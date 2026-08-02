from __future__ import annotations

import time

import boto3
from botocore.exceptions import ClientError

_TTL_SECONDS = 90 * 24 * 3600


class StateStore:
    def __init__(self, table_name: str) -> None:
        self._table = boto3.resource("dynamodb").Table(table_name)

    def put_if_absent(self, event_arn: str, issue_key: str) -> bool:
        now = int(time.time())
        try:
            self._table.put_item(
                Item={
                    "eventArn": event_arn,
                    "issueKey": issue_key,
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

    def get_issue_key(self, event_arn: str) -> str | None:
        item = self._table.get_item(Key={"eventArn": event_arn}).get("Item")
        return str(item["issueKey"]) if item else None

    def mark_closed(self, event_arn: str) -> None:
        self._table.update_item(
            Key={"eventArn": event_arn},
            UpdateExpression="SET #s = :c, updatedAt = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": "closed", ":t": int(time.time())},
        )
