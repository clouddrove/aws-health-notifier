from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    project_key: str
    issue_type: str
    default_priority: str
    priority_map: dict[str, str]
    table_name: str
    secret_arn: str
    done_transition: str


def load() -> Config:
    return Config(
        project_key=os.environ["JIRA_PROJECT_KEY"],
        issue_type=os.environ.get("JIRA_ISSUE_TYPE", "Task"),
        default_priority=os.environ.get("DEFAULT_PRIORITY", "Low"),
        priority_map=json.loads(os.environ.get("PRIORITY_MAP_JSON", "{}")),
        table_name=os.environ["TABLE_NAME"],
        secret_arn=os.environ["SECRET_ARN"],
        done_transition=os.environ.get("DONE_TRANSITION", "Done"),
    )
