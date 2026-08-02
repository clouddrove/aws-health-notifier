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


def test_description_is_adf_doc():
    doc = enrich.description(EV)
    assert doc["type"] == "doc" and doc["version"] == 1
    assert any(block["type"] == "paragraph" for block in doc["content"])
