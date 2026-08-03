from typing import Any

import pytest

from handler.config import Config


@pytest.fixture(autouse=True)
def _region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "notifiers": ["jira"],
        "github_repo": "",
        "jira_secret_arn": "arn:jira",
        "github_secret_arn": "arn:gh",
        "project_key": "OPS",
        "issue_type": "Task",
        "default_priority": "Low",
        "priority_map": {},
        "table_name": "t",
        "done_transition": "Done",
    }
    defaults.update(overrides)
    return Config(**defaults)
