import io
import json
import urllib.error
import urllib.request
from email.message import Message
from typing import Any
from unittest.mock import patch

import pytest

from handler.notifiers.github.client import GithubClient, GithubError

API = "https://api.github.com"


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
    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self._queue: list[tuple[int, dict[str, Any]]] = []

    def enqueue(self, status: int, body: dict[str, Any]) -> None:
        self._queue.append((status, body))

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _FakeResp:
        self.requests.append(req)
        status, body = self._queue.pop(0)
        payload = json.dumps(body).encode()
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "err", Message(), io.BytesIO(payload)
            )
        return _FakeResp(payload)


@pytest.fixture
def rec():
    recorder = _Recorder()
    with patch("urllib.request.urlopen", recorder):
        yield recorder


def test_create_issue_returns_number(rec):
    rec.enqueue(201, {"number": 123})
    client = GithubClient("tok")
    num = client.create_issue("o/r", "title", "body", ["priority:high"])
    assert num == "123"
    sent = json.loads(rec.requests[0].data)
    assert sent["title"] == "title" and sent["labels"] == ["priority:high"]
    assert rec.requests[0].get_header("Authorization") == "Bearer tok"
    assert rec.requests[0].full_url == f"{API}/repos/o/r/issues"


def test_ensure_label_tolerates_existing(rec):
    rec.enqueue(422, {"message": "already_exists"})
    GithubClient("tok").ensure_label("o/r", "priority:high")
    assert rec.requests[0].full_url == f"{API}/repos/o/r/labels"


def test_ensure_label_reraises_other_errors(rec):
    rec.enqueue(500, {"message": "boom"})
    with pytest.raises(GithubError, match="500"):
        GithubClient("tok").ensure_label("o/r", "priority:high")


def test_add_comment_posts(rec):
    rec.enqueue(201, {})
    GithubClient("tok").add_comment("o/r", "123", "done")
    assert rec.requests[0].full_url == f"{API}/repos/o/r/issues/123/comments"


def test_close_issue_patches_state(rec):
    rec.enqueue(200, {})
    GithubClient("tok").close_issue("o/r", "123")
    assert rec.requests[0].method == "PATCH"
    assert json.loads(rec.requests[0].data)["state"] == "closed"


def test_http_error_raises(rec):
    rec.enqueue(500, {"message": "boom"})
    with pytest.raises(GithubError, match="500"):
        GithubClient("tok").create_issue("o/r", "t", "b", [])


def test_custom_api_url_for_ghe(rec):
    rec.enqueue(201, {"number": 5})
    GithubClient("tok", "https://ghe.example.com/api/v3").create_issue("o/r", "t", "b", [])
    assert rec.requests[0].full_url == "https://ghe.example.com/api/v3/repos/o/r/issues"
