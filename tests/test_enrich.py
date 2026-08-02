from typing import Any

from handler import enrich
from handler.config import Config
from handler.events import HealthEvent

CFG = Config(
    "OPS", "Task", "Low", {"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"}, "t", "arn", "Done"
)
EV = HealthEvent(
    "arn:...abc",
    "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED",
    "open",
    "111122223333",
    "us-east-1",
    ["i-0abc123"],
    "Retirement scheduled.",
    "Wed, 1 Oct 2026 12:00:00 GMT",
    "Wed, 1 Oct 2026 14:00:00 GMT",
)


def test_priority_mapped():
    assert enrich.priority(CFG, EV) == "High"


def test_priority_default():
    ev = HealthEvent("a", "SOME_OTHER_CODE", "open", "1", "us-east-1", [], "", "", "")
    assert enrich.priority(CFG, ev) == "Low"


def test_summary_contains_instance_and_account():
    s = enrich.summary(EV)
    assert "i-0abc123" in s and "111122223333" in s


def _flatten_text(doc: dict[str, Any]) -> str:
    out = []
    for block in doc["content"]:
        for node in block.get("content", []):
            out.append(node.get("text", ""))
    return " ".join(out)


def test_description_is_adf_doc():
    doc = enrich.description(EV)
    assert doc["type"] == "doc" and doc["version"] == 1
    assert any(block["type"] == "paragraph" for block in doc["content"])


def test_description_carries_every_field():
    text = _flatten_text(enrich.description(EV))
    for expected in (
        EV.account,
        EV.region,
        EV.event_type_code,
        EV.status_code,
        EV.entities[0],
        EV.event_arn,
        EV.description,
    ):
        assert expected in text
