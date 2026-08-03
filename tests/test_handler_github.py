import json
import urllib.request
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from handler import handler

API = "https://api.github.com"
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


class _GH:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResp:
        self.paths.append(f"{req.method} {req.full_url.replace(API, '')}")
        if req.method == "POST" and req.full_url.endswith("/issues"):
            return _FakeResp(json.dumps({"number": 7}).encode())
        return _FakeResp(b"{}")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[_GH]:
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
        arn = sm.create_secret(Name="gh", SecretString=json.dumps({"token": "t"}))["ARN"]
        monkeypatch.setenv("NOTIFIERS", "github")
        monkeypatch.setenv("GITHUB_REPO", "clouddrove/x")
        monkeypatch.setenv("DEFAULT_PRIORITY", "Low")
        monkeypatch.setenv("PRIORITY_MAP_JSON", "{}")
        monkeypatch.setenv("TABLE_NAME", TABLE)
        monkeypatch.setenv("GITHUB_SECRET_ARN", arn)
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        gh = _GH()
        with patch("urllib.request.urlopen", gh):
            yield gh


def test_open_creates_github_issue(env: _GH) -> None:
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "created"
    assert any("POST /repos/clouddrove/x/issues" in p for p in env.paths)


def test_dedup_then_close(env: _GH) -> None:
    handler.lambda_handler(OPEN_EVENT, None)
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "deduped"
    closed = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "statusCode": "closed"}}
    assert handler.lambda_handler(closed, None)["status"] == "closed"
    assert any("PATCH /repos/clouddrove/x/issues/7" in p for p in env.paths)


def test_enrich_flag_is_non_fatal(env: _GH, monkeypatch: pytest.MonkeyPatch) -> None:
    # With enrichment on but no matching instance in moto, fetch fails softly and
    # returns {}, so the ticket still creates. Guards the enrich wiring.
    monkeypatch.setenv("ENRICH_TAGS", "true")
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "created"
