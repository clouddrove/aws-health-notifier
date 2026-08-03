from __future__ import annotations

from ...config import Config
from ...events import HealthEvent
from .. import priority
from . import format as jira_format
from .client import JiraClient

_RESOLVE_COMMENT = "AWS Health event resolved. Closing."


class JiraNotifier:
    def __init__(self, client: JiraClient) -> None:
        self._client = client

    def open(self, ev: HealthEvent, cfg: Config) -> str:
        return self._client.create_issue(
            cfg.project_key,
            cfg.issue_type,
            jira_format.summary(ev),
            jira_format.description(ev),
            priority.resolve(cfg, ev),
        )

    def close(self, ref: str, cfg: Config) -> None:
        self._client.add_comment(ref, _RESOLVE_COMMENT)
        self._client.transition(ref, cfg.done_transition)
