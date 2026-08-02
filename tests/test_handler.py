import io
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from email.message import Message
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from handler import handler

BASE = "https://example.atlassian.net"
TABLE = "health-jira"
SECRET = "jira-creds"

OPEN_EVENT: dict[str, Any] = {
    "source": "aws.health",
    "account": "111122223333",
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

    def __exit__(self, *args: object) -> None:
        return None


class _Jira:
    """Routes urllib calls by method+path so the handler talks to a fake Jira."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResp:
        self.requests.append(req)
        path = req.full_url.replace(BASE, "")
        if req.method == "POST" and path == "/rest/api/3/issue":
            return _FakeResp(json.dumps({"key": "OPS-1"}).encode())
        if path.endswith("/transitions") and req.method == "GET":
            return _FakeResp(json.dumps({"transitions": [{"id": "31", "name": "Done"}]}).encode())
        return _FakeResp(b"{}")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Jira]:
    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "eventArn", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "eventArn", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        sm = boto3.client("secretsmanager", region_name="us-east-1")
        arn = sm.create_secret(
            Name=SECRET,
            SecretString=json.dumps({"base_url": BASE, "email": "me@x.com", "api_token": "t"}),
        )["ARN"]
        monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
        monkeypatch.setenv("JIRA_ISSUE_TYPE", "Task")
        monkeypatch.setenv("DEFAULT_PRIORITY", "Low")
        monkeypatch.setenv(
            "PRIORITY_MAP_JSON", json.dumps({"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"})
        )
        monkeypatch.setenv("TABLE_NAME", TABLE)
        monkeypatch.setenv("SECRET_ARN", arn)
        monkeypatch.setenv("DONE_TRANSITION", "Done")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        jira = _Jira()
        with patch("urllib.request.urlopen", jira):
            yield jira


def test_open_event_creates_ticket(env: _Jira) -> None:
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "created"


def test_duplicate_event_deduped(env: _Jira) -> None:
    handler.lambda_handler(OPEN_EVENT, None)
    assert handler.lambda_handler(OPEN_EVENT, None)["status"] == "deduped"


def test_closed_event_transitions(env: _Jira) -> None:
    handler.lambda_handler(OPEN_EVENT, None)
    closed = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "statusCode": "closed"}}
    assert handler.lambda_handler(closed, None)["status"] == "closed"
    paths = [r.full_url for r in env.requests]
    assert any(p.endswith("/OPS-1/comment") for p in paths)
    assert any(p.endswith("/OPS-1/transitions") for p in paths)


def test_closed_untracked_ignored(env: _Jira) -> None:
    closed = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "statusCode": "closed"}}
    assert handler.lambda_handler(closed, None)["status"] == "ignored"


def test_non_ec2_ignored(env: _Jira) -> None:
    raw = {**OPEN_EVENT, "detail": {**OPEN_EVENT["detail"], "service": "RDS"}}
    assert handler.lambda_handler(raw, None)["status"] == "ignored"


def test_jira_failure_propagates(env: _Jira) -> None:
    from handler.jira import JiraError

    def boom(req: urllib.request.Request, timeout: float | None = None) -> _FakeResp:
        raise urllib.error.HTTPError(req.full_url, 500, "err", Message(), io.BytesIO(b"{}"))

    with patch("urllib.request.urlopen", boom), pytest.raises(JiraError):
        handler.lambda_handler(OPEN_EVENT, None)
