from __future__ import annotations

from .. import enrich
from ..config import Config
from ..events import HealthEvent
from ..jira import JiraClient

_RESOLVE_COMMENT = "AWS Health event resolved. Closing."


class JiraNotifier:
    """Adapts the low-level JiraClient to the Notifier interface."""

    def __init__(self, client: JiraClient) -> None:
        self._client = client

    def open(self, ev: HealthEvent, cfg: Config) -> str:
        return self._client.create_issue(
            cfg.project_key,
            cfg.issue_type,
            enrich.summary(ev),
            enrich.description(ev),
            enrich.priority(cfg, ev),
        )

    def close(self, ref: str, cfg: Config) -> None:
        self._client.add_comment(ref, _RESOLVE_COMMENT)
        self._client.transition(ref, cfg.done_transition)
