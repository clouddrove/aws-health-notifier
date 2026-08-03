from __future__ import annotations

from typing import Any

from ...events import HealthEvent


def summary(ev: HealthEvent) -> str:
    instances = ", ".join(ev.entities) or "unknown"
    return f"[AWS Health] {ev.event_type_code} - {instances} ({ev.account}/{ev.region})"


def _line(label: str, value: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": f"{label}: ", "marks": [{"type": "strong"}]},
            {"type": "text", "text": value or "-"},
        ],
    }


def description(ev: HealthEvent) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            _line("Account", ev.account),
            _line("Region", ev.region),
            _line("Event type", ev.event_type_code),
            _line("Status", ev.status_code),
            _line("Instances", ", ".join(ev.entities)),
            _line("Window", f"{ev.start_time} -> {ev.end_time}"),
            _line("Event ARN", ev.event_arn),
            {"type": "paragraph", "content": [{"type": "text", "text": ev.description or "-"}]},
        ],
    }
