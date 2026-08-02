from __future__ import annotations

import json
import logging
from typing import Any

from . import config, enrich, events, secrets
from .jira import JiraClient
from .state import StateStore

log = logging.getLogger()
log.setLevel(logging.INFO)


def _log(status: str, event_arn: str, **extra: object) -> None:
    log.info(json.dumps({"status": status, "eventArn": event_arn, **extra}))


def lambda_handler(event: dict[str, Any], context: object) -> dict[str, str]:
    ev = events.parse(event)
    if ev is None:
        _log("ignored", event.get("detail", {}).get("eventArn") or "unknown")
        return {"status": "ignored"}

    cfg = config.load()
    creds = secrets.load_jira(cfg.secret_arn)
    jira = JiraClient(creds["base_url"], creds["email"], creds["api_token"])
    store = StateStore(cfg.table_name)

    if ev.is_closed:
        issue_key = store.get_issue_key(ev.event_arn)
        if issue_key is None:
            _log("ignored", ev.event_arn, reason="closed-untracked")
            return {"status": "ignored"}
        jira.add_comment(issue_key, "AWS Health event resolved. Closing.")
        jira.transition(issue_key, cfg.done_transition)
        store.mark_closed(ev.event_arn)
        _log("closed", ev.event_arn, issueKey=issue_key)
        return {"status": "closed"}

    existing = store.get_issue_key(ev.event_arn)
    if existing is not None:
        _log("deduped", ev.event_arn, issueKey=existing)
        return {"status": "deduped"}

    # Create-then-store: the ticket is created before the state write. If the
    # state write raises a transient error the exception propagates and the
    # event is retried, which can create a second ticket for the same eventArn.
    # Accepted tradeoff: dedup is best-effort via put_if_absent, and Health
    # events are low volume, so a rare duplicate is cheaper than a two-phase
    # write. The conditional put still guards the common concurrent-redelivery
    # race below.
    issue_key = jira.create_issue(
        cfg.project_key,
        cfg.issue_type,
        enrich.summary(ev),
        enrich.description(ev),
        enrich.priority(cfg, ev),
    )
    if not store.put_if_absent(ev.event_arn, issue_key):
        _log("deduped", ev.event_arn, issueKey=issue_key, reason="race")
        return {"status": "deduped"}
    _log("created", ev.event_arn, issueKey=issue_key)
    return {"status": "created"}
