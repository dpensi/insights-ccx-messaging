# Copyright 2019, 2020, 2021, 2022 Red Hat Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module that implements a custom Kafka publisher."""

import json
import logging
from json import JSONDecodeError

from ccx_messaging.error import CCXMessagingError
from ccx_messaging.publishers.kafka_publisher import KafkaPublisher


log = logging.getLogger(__name__)


class RuleProcessingPublisher(KafkaPublisher):
    """
    RuleProcessingPublisher will handle the results of the applied rules and publish them to Kafka.

    The results of the data analysis are received as a JSON (string)
    and turned into a byte array using UTF-8 encoding.
    The bytes are then sent to the output Kafka topic.

    Custom error handling for the whole pipeline is implemented here.
    """

    def __init__(self, outgoing_topic, kafka_broker_config=None, **kwargs):
        """Construct a new `RuleProcessingPublisher` given `kwargs` from the config YAML."""
        super().__init__(outgoing_topic, kafka_broker_config, **kwargs)
        self.outdata_schema_version = 2

    def publish(self, input_msg, response):
        """
        Publish an EOL-terminated JSON message to the output Kafka topic.

        The response is assumed to be a string representing a valid JSON object.
        A newline character will be appended to it, it will be converted into
        a byte array using UTF-8 encoding and the result of that will be sent
        to the producer to produce a message in the output Kafka topic.
        """
        # Response is already a string, no need to JSON dump.
        output_msg = {}
        try:
            org_id = int(input_msg["identity"]["identity"]["internal"]["org_id"])
        except (ValueError, KeyError, TypeError) as err:
            raise CCXMessagingError(f"Error extracting the OrgID: {err}") from err

        try:
            account_number = int(input_msg["identity"]["identity"]["account_number"])
        except (ValueError, KeyError, TypeError) as err:
            log.warning(f"Error extracting the Account number: {err}")
            account_number = ''

        try:
            msg_timestamp = input_msg["timestamp"]
            output_msg = {
                "OrgID": org_id,
                "AccountNumber": account_number,
                "ClusterName": input_msg["cluster_name"],
                "Report": json.loads(response),
                "LastChecked": msg_timestamp,
                "Version": self.outdata_schema_version,
                "RequestId": input_msg.get("request_id"),
            }

            message = json.dumps(output_msg) + "\n"

            log.debug("Sending response to the %s topic.", self.topic)
            # Convert message string into a byte array.
            self.produce(message.encode("utf-8"))
            log.debug("Message has been sent successfully.")
            log.debug(
                "Message context: OrgId=%s, AccountNumber=%s, "
                'ClusterName="%s", LastChecked="%s, Version=%d"',
                output_msg["OrgID"],
                output_msg["AccountNumber"],
                output_msg["ClusterName"],
                output_msg["LastChecked"],
                output_msg["Version"],
            )

            log.info(
                "Status: Success; "
                "Topic: %s; "
                "Partition: %s; "
                "Offset: %s; "
                "LastChecked: %s",
                input_msg.get("topic"),
                input_msg.get("partition"),
                input_msg.get("offset"),
                msg_timestamp,
            )

        except KeyError as err:
            raise CCXMessagingError("Missing expected keys in the input message") from err

        except (TypeError, UnicodeEncodeError, JSONDecodeError) as err:
            raise CCXMessagingError(f"Error encoding the response to publish: {response}") from err
