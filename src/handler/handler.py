from __future__ import annotations

from typing import Any

from . import config, events, notifiers
from . import logging as structured_log
from .state import StateStore


def lambda_handler(event: dict[str, Any], context: object) -> dict[str, str]:
    ev = events.parse(event)
    if ev is None:
        structured_log.emit("ignored", event.get("detail", {}).get("eventArn") or "unknown")
        return {"status": "ignored"}

    cfg = config.load()
    notifier = notifiers.build(cfg)
    store = StateStore(cfg.table_name)

    if ev.is_closed:
        record = store.get_record(ev.event_arn)
        if record is None:
            structured_log.emit("ignored", ev.event_arn, reason="closed-untracked")
            return {"status": "ignored"}
        ref, status = record
        if status == "closed":
            # Already closed on a prior delivery; skip to stay idempotent and
            # avoid duplicate resolution comments on redelivery.
            structured_log.emit("deduped", ev.event_arn, ref=ref, reason="already-closed")
            return {"status": "deduped"}
        notifier.close(ref, cfg)
        store.mark_closed(ev.event_arn)
        structured_log.emit("closed", ev.event_arn, ref=ref)
        return {"status": "closed"}

    existing = store.get_issue_key(ev.event_arn)
    if existing is not None:
        structured_log.emit("deduped", ev.event_arn, ref=existing)
        return {"status": "deduped"}

    # Create-then-store: the ticket is created before the state write. If the
    # state write raises a transient error the exception propagates and the
    # event is retried, which can create a second ticket for the same eventArn.
    # Accepted tradeoff: dedup is best-effort via put_if_absent, and Health
    # events are low volume, so a rare duplicate is cheaper than a two-phase
    # write. The conditional put still guards the common concurrent-redelivery
    # race below.
    ref = notifier.open(ev, cfg)
    if not store.put_if_absent(ev.event_arn, ref):
        structured_log.emit("deduped", ev.event_arn, ref=ref, reason="race")
        return {"status": "deduped"}
    structured_log.emit("created", ev.event_arn, ref=ref)
    return {"status": "created"}
