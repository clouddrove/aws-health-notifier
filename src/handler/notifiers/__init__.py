from __future__ import annotations

from .. import secrets
from ..config import Config
from .base import Notifier, NotifierError
from .github.client import GithubClient
from .github.notifier import GithubNotifier
from .jira.client import JiraClient
from .jira.notifier import JiraNotifier


def build(cfg: Config) -> Notifier:
    """Construct the Notifier selected by cfg.notifier."""
    if cfg.notifier == "jira":
        if not cfg.project_key:
            raise ValueError("notifier 'jira' requires JIRA_PROJECT_KEY")
        creds = secrets.load(cfg.secret_arn)
        return JiraNotifier(JiraClient(creds["base_url"], creds["email"], creds["api_token"]))
    if cfg.notifier == "github":
        if not cfg.github_repo:
            raise ValueError("notifier 'github' requires GITHUB_REPO")
        creds = secrets.load(cfg.secret_arn)
        client = GithubClient(creds["token"], creds.get("api_url", "https://api.github.com"))
        return GithubNotifier(client, cfg.github_repo)
    raise ValueError(f"unknown notifier: {cfg.notifier}")


__all__ = ["Notifier", "NotifierError", "build"]
