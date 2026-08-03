from __future__ import annotations

from ...config import Config
from ...enrichment import tags as tag_util
from ...events import HealthEvent
from .. import priority


def summary(ev: HealthEvent) -> str:
    instances = ", ".join(ev.entities) or "unknown"
    return f"[AWS Health] {ev.event_type_code} - {instances} ({ev.account}/{ev.region})"


def body(ev: HealthEvent) -> str:
    lines = [
        f"**Account**: {ev.account}",
        f"**Region**: {ev.region}",
        f"**Event type**: {ev.event_type_code}",
        f"**Status**: {ev.status_code}",
        f"**Instances**: {', '.join(ev.entities) or '-'}",
        f"**Window**: {ev.start_time} -> {ev.end_time}",
        f"**Event ARN**: {ev.event_arn}",
    ]
    tagged = {iid: pairs for iid, pairs in ev.instance_tags.items() if pairs}
    if tagged:
        lines.append("")
        lines.append("Instance tags:")
        for iid, pairs in tagged.items():
            lines.append(f"- **{iid}**: {tag_util.format_pairs(pairs)}")
    lines.append("")
    lines.append(ev.description or "-")
    return "\n".join(lines)


def priority_label(cfg: Config, ev: HealthEvent) -> str:
    return f"priority:{priority.resolve(cfg, ev).lower()}"
