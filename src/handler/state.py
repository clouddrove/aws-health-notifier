from __future__ import annotations

import time
from dataclasses import dataclass

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

_TTL_SECONDS = 90 * 24 * 3600


@dataclass(frozen=True)
class SinkRef:
    sink: str
    ref: str
    status: str


class StateStore:
    def __init__(self, table_name: str) -> None:
        self._table = boto3.resource("dynamodb").Table(table_name)

    def put_if_absent(self, event_arn: str, sink: str, ref: str) -> bool:
        now = int(time.time())
        try:
            self._table.put_item(
                Item={
                    "eventArn": event_arn,
                    "sink": sink,
                    "ref": ref,
                    "status": "open",
                    "updatedAt": now,
                    "ttl": now + _TTL_SECONDS,
                },
                ConditionExpression="attribute_not_exists(eventArn)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def get_refs(self, event_arn: str) -> list[SinkRef]:
        items = self._table.query(KeyConditionExpression=Key("eventArn").eq(event_arn)).get(
            "Items", []
        )
        return [SinkRef(str(i["sink"]), str(i["ref"]), str(i["status"])) for i in items]

    def mark_closed(self, event_arn: str, sink: str) -> None:
        self._table.update_item(
            Key={"eventArn": event_arn, "sink": sink},
            UpdateExpression="SET #s = :c, updatedAt = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": "closed", ":t": int(time.time())},
        )
