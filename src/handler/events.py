from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_CLOSED = {"closed", "resolved"}


@dataclass(frozen=True)
class HealthEvent:
    event_arn: str
    event_type_code: str
    status_code: str
    account: str
    region: str
    entities: list[str]
    description: str
    start_time: str
    end_time: str

    @property
    def is_closed(self) -> bool:
        return self.status_code.lower() in _CLOSED


def parse(raw: dict[str, Any]) -> HealthEvent | None:
    if raw.get("source") != "aws.health":
        return None
    detail = raw.get("detail", {})
    if detail.get("service") != "EC2":
        return None
    descriptions = detail.get("eventDescription", [])
    description = descriptions[0].get("latestDescription", "") if descriptions else ""
    entities = [e.get("entityValue", "") for e in detail.get("affectedEntities", [])]
    return HealthEvent(
        event_arn=detail["eventArn"],
        event_type_code=detail.get("eventTypeCode", ""),
        status_code=detail.get("statusCode", "open"),
        account=raw.get("account", ""),
        region=raw.get("region", ""),
        entities=entities,
        description=description,
        start_time=detail.get("startTime", ""),
        end_time=detail.get("endTime", ""),
    )
