from handler.events import HealthEvent
from handler.notifiers.github import format as gh
from tests.conftest import make_config

CFG = make_config(
    notifiers=["github"],
    github_repo="clouddrove/x",
    priority_map={"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"},
)
EV = HealthEvent(
    "arn:abc",
    "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED",
    "open",
    "111122223333",
    "us-east-1",
    ["i-0abc"],
    "Retire.",
    "s",
    "e",
)


def test_summary_has_instance_and_account():
    s = gh.summary(EV)
    assert "i-0abc" in s and "111122223333" in s


def test_body_markdown_carries_fields():
    b = gh.body(EV)
    for expected in ("111122223333", "us-east-1", "i-0abc", "arn:abc", "Retire."):
        assert expected in b
    assert "**Account**" in b


def test_priority_label_lowercased():
    assert gh.priority_label(CFG, EV) == "priority:high"


def test_priority_label_default():
    ev = HealthEvent("a", "OTHER", "open", "1", "us-east-1", [], "", "", "")
    assert gh.priority_label(CFG, ev) == "priority:low"
