from collections.abc import Iterator

import boto3
import pytest
from boto3.dynamodb.conditions import Key
from moto import mock_aws

from handler.state import StateStore

TABLE = "health-notifier"


def _create_table() -> None:
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName=TABLE,
        KeySchema=[
            {"AttributeName": "eventArn", "KeyType": "HASH"},
            {"AttributeName": "sink", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "eventArn", "AttributeType": "S"},
            {"AttributeName": "sink", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def store() -> Iterator[StateStore]:
    with mock_aws():
        _create_table()
        yield StateStore(TABLE)


def test_put_if_absent_per_sink(store: StateStore) -> None:
    assert store.put_if_absent("arn1", "jira", "OPS-1") is True
    assert store.put_if_absent("arn1", "jira", "OPS-2") is False
    assert store.put_if_absent("arn1", "github", "7") is True


def test_get_refs_returns_all_sinks(store: StateStore) -> None:
    store.put_if_absent("arn1", "jira", "OPS-1")
    store.put_if_absent("arn1", "github", "7")
    refs = {r.sink: r for r in store.get_refs("arn1")}
    assert refs["jira"].ref == "OPS-1" and refs["jira"].status == "open"
    assert refs["github"].ref == "7"


def test_get_refs_empty(store: StateStore) -> None:
    assert store.get_refs("nope") == []


def test_mark_closed_one_sink(store: StateStore) -> None:
    store.put_if_absent("arn1", "jira", "OPS-1")
    store.put_if_absent("arn1", "github", "7")
    store.mark_closed("arn1", "jira")
    refs = {r.sink: r.status for r in store.get_refs("arn1")}
    assert refs["jira"] == "closed"
    assert refs["github"] == "open"


def test_ttl_is_int(store: StateStore) -> None:
    store.put_if_absent("arn1", "jira", "OPS-1")
    raw = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    item = raw.query(KeyConditionExpression=Key("eventArn").eq("arn1"))["Items"][0]
    assert int(str(item["ttl"])) > int(str(item["updatedAt"]))
