import json
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from handler import notifiers
from handler.config import Config
from handler.events import HealthEvent
from handler.notifiers.jira.client import JiraClient
from handler.notifiers.jira.notifier import JiraNotifier

CFG = Config(
    "jira",
    "",
    "OPS",
    "Task",
    "Low",
    {"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"},
    "t",
    "arn",
    "Done",
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
        self.created: dict[str, Any] = {}
        self.comments: list[tuple[str, str]] = []
        self.transitions: list[tuple[str, str]] = []

    def create_issue(self, project_key, issue_type, summary, description, priority) -> str:
        self.created = {"project": project_key, "priority": priority, "summary": summary}
        return "OPS-9"

    def add_comment(self, ref, text) -> None:
        self.comments.append((ref, text))

    def transition(self, ref, name) -> None:
        self.transitions.append((ref, name))


def test_jira_notifier_open_uses_enrichment() -> None:
    client = _Client()
    ref = JiraNotifier(client).open(EV, CFG)  # type: ignore[arg-type]
    assert ref == "OPS-9"
    assert client.created["priority"] == "High"
    assert "i-0abc" in client.created["summary"]


def test_jira_notifier_close_comments_and_transitions() -> None:
    client = _Client()
    JiraNotifier(client).close("OPS-9", CFG)  # type: ignore[arg-type]
    assert client.comments[0][0] == "OPS-9"
    assert client.transitions[0] == ("OPS-9", "Done")


def test_build_unknown_notifier_raises() -> None:
    cfg = Config("slack", "", "OPS", "Task", "Low", {}, "t", "arn", "Done")
    with pytest.raises(ValueError, match="unknown notifier"):
        notifiers.build(cfg)


def test_build_jira_without_project_key_raises() -> None:
    cfg = Config("jira", "", "", "Task", "Low", {}, "t", "arn", "Done")
    with pytest.raises(ValueError, match="requires JIRA_PROJECT_KEY"):
        notifiers.build(cfg)


def test_build_jira_reads_secret() -> None:
    with mock_aws():
        sm = boto3.client("secretsmanager", region_name="us-east-1")
        arn = sm.create_secret(
            Name="creds",
            SecretString=json.dumps(
                {"base_url": "https://x.atlassian.net", "email": "e", "api_token": "t"}
            ),
        )["ARN"]
        cfg = Config("jira", "", "OPS", "Task", "Low", {}, "t", arn, "Done")
        with patch.dict("os.environ", {"AWS_DEFAULT_REGION": "us-east-1"}):
            notifier = notifiers.build(cfg)
        assert isinstance(notifier, JiraNotifier)
        assert isinstance(notifier._client, JiraClient)  # noqa: SLF001
