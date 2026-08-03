from typing import Any

from handler.events import HealthEvent
from handler.notifiers.github.notifier import GithubNotifier
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
    "1",
    "us-east-1",
    ["i-0abc"],
    "d",
    "s",
    "e",
)


class _Client:
    def __init__(self) -> None:
        self.labels: list[tuple[str, str]] = []
        self.created: dict[str, Any] = {}
        self.comments: list[tuple[str, str]] = []
        self.closed: list[tuple[str, str]] = []

    def ensure_label(self, repo: str, name: str) -> None:
        self.labels.append((repo, name))

    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        self.created = {"repo": repo, "labels": labels, "title": title}
        return "123"

    def add_comment(self, repo: str, number: str, body: str) -> None:
        self.comments.append((repo, number))

    def close_issue(self, repo: str, number: str) -> None:
        self.closed.append((repo, number))


def test_open_ensures_label_and_creates() -> None:
    c = _Client()
    ref = GithubNotifier(c, "clouddrove/x").open(EV, CFG)  # type: ignore[arg-type]
    assert ref == "123"
    assert c.labels == [("clouddrove/x", "priority:high")]
    assert c.created["labels"] == ["priority:high"]


def test_close_comments_then_closes() -> None:
    c = _Client()
    GithubNotifier(c, "clouddrove/x").close("123", CFG)  # type: ignore[arg-type]
    assert c.comments == [("clouddrove/x", "123")]
    assert c.closed == [("clouddrove/x", "123")]
