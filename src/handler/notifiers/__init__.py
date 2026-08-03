from __future__ import annotations

from .. import secrets
from ..config import Config
from .base import Notifier, NotifierError
from .jira.client import JiraClient
from .jira.notifier import JiraNotifier


def build(cfg: Config) -> Notifier:
    """Construct the Notifier selected by cfg.notifier."""
    if cfg.notifier == "jira":
        creds = secrets.load(cfg.secret_arn)
        return JiraNotifier(JiraClient(creds["base_url"], creds["email"], creds["api_token"]))
    raise ValueError(f"unknown notifier: {cfg.notifier}")


__all__ = ["Notifier", "NotifierError", "build"]
