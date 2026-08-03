from __future__ import annotations

from ...config import Config
from ...events import HealthEvent
from . import format as gh_format
from .client import GithubClient

_RESOLVE_COMMENT = "AWS Health event resolved. Closing."


class GithubNotifier:
    def __init__(self, client: GithubClient, repo: str) -> None:
        self._client = client
        self._repo = repo

    def open(self, ev: HealthEvent, cfg: Config) -> str:
        label = gh_format.priority_label(cfg, ev)
        self._client.ensure_label(self._repo, label)
        return self._client.create_issue(
            self._repo, gh_format.summary(ev), gh_format.body(ev), [label]
        )

    def close(self, ref: str, cfg: Config) -> None:
        self._client.add_comment(self._repo, ref, _RESOLVE_COMMENT)
        self._client.close_issue(self._repo, ref)
