import pytest

from handler import config


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("SECRET_ARN", "arn")


def test_github_repo_parsed(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("NOTIFIER", "github")
    monkeypatch.setenv("GITHUB_REPO", "clouddrove/x")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "")
    cfg = config.load()
    assert cfg.notifier == "github"
    assert cfg.github_repo == "clouddrove/x"


def test_jira_defaults(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("NOTIFIER", raising=False)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
    cfg = config.load()
    assert cfg.notifier == "jira"
    assert cfg.github_repo == ""
