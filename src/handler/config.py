from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    notifiers: list[str]
    github_repo: str
    jira_secret_arn: str
    github_secret_arn: str
    project_key: str
    issue_type: str
    default_priority: str
    priority_map: dict[str, str]
    table_name: str
    done_transition: str


def parse_notifiers(raw: str) -> list[str]:
    seen: list[str] = []
    for part in raw.split(","):
        name = part.strip().lower()
        if name and name not in seen:
            seen.append(name)
    return seen


def _load_priority_map() -> dict[str, str]:
    parsed = json.loads(os.environ.get("PRIORITY_MAP_JSON", "{}"))
    if not isinstance(parsed, dict):
        raise ValueError("PRIORITY_MAP_JSON must be a JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def load() -> Config:
    return Config(
        notifiers=parse_notifiers(os.environ.get("NOTIFIERS", "jira")),
        github_repo=os.environ.get("GITHUB_REPO", ""),
        jira_secret_arn=os.environ.get("JIRA_SECRET_ARN", ""),
        github_secret_arn=os.environ.get("GITHUB_SECRET_ARN", ""),
        project_key=os.environ.get("JIRA_PROJECT_KEY", ""),
        issue_type=os.environ.get("JIRA_ISSUE_TYPE", "Task"),
        default_priority=os.environ.get("DEFAULT_PRIORITY", "Low"),
        priority_map=_load_priority_map(),
        table_name=os.environ["TABLE_NAME"],
        done_transition=os.environ.get("DONE_TRANSITION", "Done"),
    )
