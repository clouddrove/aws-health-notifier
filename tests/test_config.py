import pytest

from handler import config


def _env(monkeypatch: pytest.MonkeyPatch, **kw: str) -> None:
    monkeypatch.setenv("TABLE_NAME", "t")
    for k, v in kw.items():
        monkeypatch.setenv(k, v)


def test_notifiers_default_jira(monkeypatch):
    _env(monkeypatch)
    assert config.load().notifiers == ["jira"]


def test_notifiers_list_parsed(monkeypatch):
    _env(monkeypatch, NOTIFIERS="jira, github , jira")
    assert config.load().notifiers == ["jira", "github"]


def test_parse_notifiers_helper():
    assert config.parse_notifiers("GitHub, ,jira") == ["github", "jira"]


def test_per_sink_secret_arns(monkeypatch):
    _env(monkeypatch, JIRA_SECRET_ARN="arn:j", GITHUB_SECRET_ARN="arn:g", GITHUB_REPO="o/r")
    cfg = config.load()
    assert cfg.jira_secret_arn == "arn:j"
    assert cfg.github_secret_arn == "arn:g"
    assert cfg.github_repo == "o/r"
