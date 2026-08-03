from __future__ import annotations

from ..config import Config
from ..events import HealthEvent


def resolve(cfg: Config, ev: HealthEvent) -> str:
    return cfg.priority_map.get(ev.event_type_code, cfg.default_priority)
