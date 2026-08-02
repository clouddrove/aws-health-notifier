import io
import json
import urllib.error
import urllib.request
from email.message import Message
from typing import Any
from unittest.mock import patch

import pytest

from handler.jira import JiraClient, JiraError

BASE = "https://example.atlassian.net"


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Recorder:
    """Queue of (status, json-body) replies for urllib.request.urlopen."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self._queue: list[tuple[int, bytes]] = []

    def enqueue(self, status: int, body: dict[str, Any]) -> None:
        self._queue.append((status, json.dumps(body).encode()))

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResp:
        self.requests.append(req)
        status, body = self._queue.pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "err", Message(), io.BytesIO(body))
        return _FakeResp(body)


@pytest.fixture
def rec():
    recorder = _Recorder()
    with patch("urllib.request.urlopen", recorder):
        yield recorder


def test_create_issue_returns_key(rec):
    rec.enqueue(201, {"key": "OPS-42"})
    client = JiraClient(BASE, "me@x.com", "token")
    key = client.create_issue(
        "OPS", "Task", "sum", {"type": "doc", "version": 1, "content": []}, "High"
    )
    assert key == "OPS-42"
    body = json.loads(rec.requests[0].data)
    assert body["fields"]["project"]["key"] == "OPS"
    assert body["fields"]["priority"]["name"] == "High"
    assert rec.requests[0].get_header("Authorization").startswith("Basic ")


def test_add_comment(rec):
    rec.enqueue(201, {})
    JiraClient(BASE, "me@x.com", "token").add_comment("OPS-42", "resolved")
    assert rec.requests[0].full_url.endswith("/OPS-42/comment")
    assert rec.requests[0].method == "POST"


def test_transition_looks_up_id(rec):
    rec.enqueue(200, {"transitions": [{"id": "31", "name": "Done"}]})
    rec.enqueue(204, {})
    JiraClient(BASE, "me@x.com", "token").transition("OPS-42", "Done")
    posted = json.loads(rec.requests[1].data)
    assert posted["transition"]["id"] == "31"


def test_transition_noop_when_name_absent(rec):
    rec.enqueue(200, {"transitions": [{"id": "31", "name": "In Progress"}]})
    JiraClient(BASE, "me@x.com", "token").transition("OPS-42", "Done")
    assert len(rec.requests) == 1


def test_http_error_raises_jira_error(rec):
    rec.enqueue(400, {"errors": {"x": "bad"}})
    with pytest.raises(JiraError, match="400"):
        JiraClient(BASE, "me@x.com", "token").create_issue(
            "OPS", "Task", "s", {"type": "doc", "version": 1, "content": []}, "Low"
        )
