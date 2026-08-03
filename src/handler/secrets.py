from __future__ import annotations

import json
from typing import Any

import boto3


def load_jira(secret_arn: str) -> dict[str, Any]:
    client = boto3.client("secretsmanager")
    raw = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    result: dict[str, Any] = json.loads(raw)
    return result
