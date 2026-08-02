import json

from handler import config, events

RAW = {
    "detail-type": "AWS Health Event",
    "source": "aws.health",
    "account": "111122223333",
    "region": "us-east-1",
    "detail": {
        "eventArn": "arn:aws:health:us-east-1::event/EC2/AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED/abc",
        "service": "EC2",
        "eventTypeCode": "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED",
        "eventTypeCategory": "scheduledChange",
        "statusCode": "open",
        "startTime": "Wed, 1 Oct 2026 12:00:00 GMT",
        "endTime": "Wed, 1 Oct 2026 14:00:00 GMT",
        "eventDescription": [
            {"language": "en_US", "latestDescription": "Your instance is scheduled for retirement."}
        ],
        "affectedEntities": [{"entityValue": "i-0abc123"}],
    },
}


def test_parse_extracts_fields():
    ev = events.parse(RAW)
    assert ev is not None
    assert ev.event_type_code == "AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED"
    assert ev.status_code == "open"
    assert ev.account == "111122223333"
    assert ev.entities == ["i-0abc123"]


def test_parse_ignores_non_ec2():
    raw = {**RAW, "detail": {**RAW["detail"], "service": "RDS"}}
    assert events.parse(raw) is None


def test_config_priority_map(monkeypatch):
    monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
    monkeypatch.setenv("JIRA_ISSUE_TYPE", "Task")
    monkeypatch.setenv("DEFAULT_PRIORITY", "Low")
    monkeypatch.setenv(
        "PRIORITY_MAP_JSON", json.dumps({"AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED": "High"})
    )
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("SECRET_ARN", "arn:secret")
    monkeypatch.setenv("DONE_TRANSITION", "Done")
    cfg = config.load()
    assert cfg.priority_map["AWS_EC2_INSTANCE_RETIREMENT_SCHEDULED"] == "High"
    assert cfg.default_priority == "Low"
