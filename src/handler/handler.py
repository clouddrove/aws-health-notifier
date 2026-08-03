from __future__ import annotations

from typing import Any

from . import config, events, notifiers
from . import logging as structured_log
from .enrichment import tags
from .state import StateStore


def lambda_handler(event: dict[str, Any], context: object) -> dict[str, str]:
    ev = events.parse(event)
    if ev is None:
        structured_log.emit("ignored", event.get("detail", {}).get("eventArn") or "unknown")
        return {"status": "ignored"}

    cfg = config.load()
    ev = tags.with_tags(ev, cfg)
    built = notifiers.build_all(cfg)
    store = StateStore(cfg.table_name)

    if ev.is_closed:
        refs = store.get_refs(ev.event_arn)
        if not refs:
            structured_log.emit("ignored", ev.event_arn, reason="closed-untracked")
            return {"status": "ignored"}
        by_name = dict(built)
        closed_any = False
        for sr in refs:
            if sr.status == "closed":
                continue
            notifier = by_name.get(sr.sink)
            if notifier is None:
                structured_log.emit("skipped", ev.event_arn, sink=sr.sink, reason="not-configured")
                continue
            notifier.close(sr.ref, cfg)
            store.mark_closed(ev.event_arn, sr.sink)
            structured_log.emit("closed", ev.event_arn, sink=sr.sink, ref=sr.ref)
            closed_any = True
        return {"status": "closed" if closed_any else "deduped"}

    existing = {sr.sink for sr in store.get_refs(ev.event_arn)}
    created_any = False
    for name, notifier in built:
        if name in existing:
            structured_log.emit("deduped", ev.event_arn, sink=name)
            continue
        # Create-then-store per sink: each sink's ref is persisted before the
        # next sink runs, so a transient failure retries only the unfinished
        # sinks rather than duplicating the ones that already succeeded.
        ref = notifier.open(ev, cfg)
        if store.put_if_absent(ev.event_arn, name, ref):
            structured_log.emit("created", ev.event_arn, sink=name, ref=ref)
            created_any = True
        else:
            structured_log.emit("deduped", ev.event_arn, sink=name, ref=ref, reason="race")
    return {"status": "created" if created_any else "deduped"}
