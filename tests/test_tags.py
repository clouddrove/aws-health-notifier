import boto3
from moto import mock_aws

from handler.enrichment import tags
from handler.events import HealthEvent
from tests.conftest import make_config


def test_format_pairs():
    assert (
        tags.format_pairs({"Name": "web-01", "Environment": "prod"})
        == "Name=web-01, Environment=prod"
    )


def _launch_instance_with_tags() -> str:
    ec2 = boto3.resource("ec2", region_name="us-east-1")
    inst = ec2.create_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "web-01"},
                    {"Key": "Environment", "Value": "prod"},
                    {"Key": "Other", "Value": "ignore"},
                ],
            }
        ],
    )[0]
    return str(inst.id)


def test_fetch_returns_filtered_tags():
    with mock_aws():
        iid = _launch_instance_with_tags()
        cfg = make_config(enrich_tags=True, tag_keys=["Name", "Environment"])
        # moto isolates accounts; assume into its default account so the ec2
        # client sees the instance launched above.
        result = tags.fetch("123456789012", "us-east-1", [iid], cfg)
        assert result[iid] == {"Name": "web-01", "Environment": "prod"}


def test_fetch_error_returns_empty(monkeypatch):
    cfg = make_config(enrich_tags=True)

    def boom(*a, **k):
        raise RuntimeError("sts down")

    monkeypatch.setattr("handler.enrichment.tags.boto3.client", boom)
    assert tags.fetch("1", "us-east-1", ["i-x"], cfg) == {}


def test_with_tags_noop_when_flag_off():
    ev = HealthEvent("a", "T", "open", "1", "us-east-1", ["i-x"], "d", "s", "e")
    cfg = make_config(enrich_tags=False)
    assert tags.with_tags(ev, cfg) is ev


def test_with_tags_populates_when_on():
    with mock_aws():
        iid = _launch_instance_with_tags()
        ev = HealthEvent("a", "T", "open", "123456789012", "us-east-1", [iid], "d", "s", "e")
        cfg = make_config(enrich_tags=True)
        out = tags.with_tags(ev, cfg)
        assert out.instance_tags[iid]["Name"] == "web-01"
