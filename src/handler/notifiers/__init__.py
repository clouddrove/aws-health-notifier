from __future__ import annotations

from .. import secrets
from ..config import Config
from ..jira import JiraClient
from .base import Notifier
from .jira_notifier import JiraNotifier


def build(cfg: Config) -> Notifier:
    """Construct the Notifier selected by cfg.notifier."""
    if cfg.notifier == "jira":
        creds = secrets.load_jira(cfg.secret_arn)
        client = JiraClient(creds["base_url"], creds["email"], creds["api_token"])
        return JiraNotifier(client)
    raise ValueError(f"unknown notifier: {cfg.notifier}")


__all__ = ["Notifier", "build"]
