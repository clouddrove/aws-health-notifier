import json
import urllib.request
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from handler import handler

JIRA = "https://x.atlassian.net"
GH = "https://api.github.com"
TABLE = "state"

OPEN_EVENT: dict[str, Any] = {
    "source": "aws.health",
    "account": "1",
    "region": "us-east-1",
    "detail": {
        "eventArn": "arn:health:EC2/RETIRE/abc",
        "service": "EC2",
        "eventTypeCode": "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED",
        "statusCode": "open",
        "startTime": "s",
        "endTime": "e",
        "eventDescription": [{"latestDescription": "retire"}],
        "affectedEntities": [{"entityValue": "i-0abc"}],
    },
}


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *a: object) -> None:
        return None


class _Router:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResp:
        url = req.full_url
        self.calls.append(f"{req.method} {url}")
        if url.startswith(JIRA) and req.method == "POST" and url.endswith("/issue"):
            return _FakeResp(json.dumps({"key": "OPS-1"}).encode())
        if url.startswith(GH) and req.method == "POST" and url.endswith("/issues"):
            return _FakeResp(json.dumps({"number": 7}).encode())
        if url.endswith("/transitions") and req.method == "GET":
            return _FakeResp(json.dumps({"transitions": [{"id": "31", "name": "Done"}]}).encode())
        return _FakeResp(b"{}")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Router]:
    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "eventArn", "KeyType": "HASH"},
                {"AttributeName": "sink", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "eventArn", "AttributeType": "S"},
                {"AttributeName": "sink", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        sm = boto3.client("secretsmanager", region_name="us-east-1")
        ja = sm.create_secret(
            Name="j",
            SecretString=json.dumps({"base_url": JIRA, "email": "e", "api_token": "t"}),
        )["ARN"]
        ga = sm.create_secret(Name="g", SecretString=json.dumps({"token": "t"}))["ARN"]
        monkeypatch.setenv("NOTIFIERS", "jira,github")
        monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
        monkeypatch.setenv("GITHUB_REPO", "clouddrove/x")
        monkeypatch.setenv("JIRA_SECRET_ARN", ja)
        monkeypatch.setenv("GITHUB_SECRET_ARN", ga)
        monkeypatch.setenv("DEFAULT_PRIORITY", "Low")
        monkeypatch.setenv("PRIORITY_MAP_JSON", "{}")
        monkeypatch.setenv("TABLE_NAME", TABLE)
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        router = _Router()
        with patch("urllib.request.urlopen", router):
            yield router


def test_fanout_creates_in_both(env: _Router) -> None:
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "created"
    assert any(c.startswith("POST " + JIRA) and c.endswith("/issue") for c in env.calls)
    assert any(c.startswith("POST " + GH) and c.endswith("/issues") for c in env.calls)


def test_fanout_dedup_second_delivery(env: _Router) -> None:
    handler.lambda_handler(OPEN_EVENT, None)
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "deduped"


def test_fanout_closes_both(env: _Router) -> None:
    handler.lambda_handler(OPEN_EVENT, None)
    closed = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "statusCode": "closed"}}
    assert handler.lambda_handler(closed, None)["status"] == "closed"
    assert any("/OPS-1/transitions" in c for c in env.calls)
    assert any("PATCH " + GH + "/repos/clouddrove/x/issues/7" in c for c in env.calls)
