from __future__ import annotations

from .. import secrets
from ..config import Config
from .base import Notifier, NotifierError
from .github.client import GithubClient
from .github.notifier import GithubNotifier
from .jira.client import JiraClient
from .jira.notifier import JiraNotifier


def _build_one(cfg: Config, name: str) -> Notifier:
    if name == "jira":
        if not cfg.project_key:
            raise ValueError("notifier 'jira' requires JIRA_PROJECT_KEY")
        creds = secrets.load(cfg.jira_secret_arn)
        return JiraNotifier(JiraClient(creds["base_url"], creds["email"], creds["api_token"]))
    if name == "github":
        if not cfg.github_repo:
            raise ValueError("notifier 'github' requires GITHUB_REPO")
        creds = secrets.load(cfg.github_secret_arn)
        client = GithubClient(creds["token"], creds.get("api_url", "https://api.github.com"))
        return GithubNotifier(client, cfg.github_repo)
    raise ValueError(f"unknown notifier: {name}")


def build_all(cfg: Config) -> list[tuple[str, Notifier]]:
    """Build one Notifier per configured name, in order."""
    return [(name, _build_one(cfg, name)) for name in cfg.notifiers]


__all__ = ["Notifier", "NotifierError", "build_all"]
