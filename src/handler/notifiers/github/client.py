from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..base import NotifierError


class GithubError(NotifierError):
    pass


class GithubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self._base = api_url.rstrip("/")
        self._token = token

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"{self._base}{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                body = resp.read()
                result: dict[str, Any] = json.loads(body) if body else {}
                return result
        except urllib.error.HTTPError as exc:
            raise GithubError(
                f"{method} {path} -> {exc.code}: {exc.read().decode()}", status=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            raise GithubError(f"{method} {path} -> network error: {exc.reason}") from exc

    def ensure_label(self, repo: str, name: str) -> None:
        try:
            self._request("POST", f"/repos/{repo}/labels", {"name": name})
        except GithubError as exc:
            if exc.status != 422:  # 422 means the label already exists
                raise

    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        payload = {"title": title, "body": body, "labels": labels}
        number = self._request("POST", f"/repos/{repo}/issues", payload)["number"]
        return str(number)

    def add_comment(self, repo: str, number: str, body: str) -> None:
        self._request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})

    def close_issue(self, repo: str, number: str) -> None:
        self._request("PATCH", f"/repos/{repo}/issues/{number}", {"state": "closed"})
