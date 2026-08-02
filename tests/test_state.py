from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from handler.state import StateStore

TABLE = "health-jira"


@pytest.fixture
def table() -> Iterator[StateStore]:
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "eventArn", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "eventArn", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield StateStore(TABLE)


def test_put_if_absent_first_wins(table: StateStore) -> None:
    assert table.put_if_absent("arn1", "OPS-1") is True
    assert table.put_if_absent("arn1", "OPS-2") is False
    assert table.get_issue_key("arn1") == "OPS-1"


def test_get_missing_returns_none(table: StateStore) -> None:
    assert table.get_issue_key("nope") is None


def test_mark_closed(table: StateStore) -> None:
    table.put_if_absent("arn1", "OPS-1")
    table.mark_closed("arn1")
    assert table.get_issue_key("arn1") == "OPS-1"
    raw = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    item = raw.get_item(Key={"eventArn": "arn1"})["Item"]
    assert item["status"] == "closed"


def test_put_stores_int_ttl(table: StateStore) -> None:
    table.put_if_absent("arn1", "OPS-1")
    raw = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    item = raw.get_item(Key={"eventArn": "arn1"})["Item"]
    assert item["ttl"] > item["updatedAt"]


def test_client_error_other_than_condition_reraises(table: StateStore) -> None:
    from unittest.mock import patch

    from botocore.exceptions import ClientError

    err = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem")
    with (
        patch.object(table._table, "put_item", side_effect=err),  # noqa: SLF001
        pytest.raises(ClientError),
    ):
        table.put_if_absent("arn2", "OPS-2")
