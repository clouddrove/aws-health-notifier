from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from ..base import NotifierError


class JiraError(NotifierError):
    pass


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self._base = base_url.rstrip("/")
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth = f"Basic {token}"

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"{self._base}{path}", data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                body = resp.read()
                result: dict[str, Any] = json.loads(body) if body else {}
                return result
        except urllib.error.HTTPError as exc:
            raise JiraError(
                f"{method} {path} -> {exc.code}: {exc.read().decode()}", status=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            raise JiraError(f"{method} {path} -> network error: {exc.reason}") from exc

    def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        description: dict[str, Any],
        priority: str,
    ) -> str:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "description": description,
                "priority": {"name": priority},
            }
        }
        key: str = self._request("POST", "/rest/api/3/issue", payload)["key"]
        return key

    def add_comment(self, issue_key: str, text: str) -> None:
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
            }
        }
        self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", payload)

    def transition(self, issue_key: str, transition_name: str) -> None:
        data = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        match = next((t for t in data.get("transitions", []) if t["name"] == transition_name), None)
        if match is None:
            return
        self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            {"transition": {"id": match["id"]}},
        )
