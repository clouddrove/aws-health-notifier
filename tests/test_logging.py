import json
import logging

from handler import logging as structured_log


def test_emit_writes_json(caplog):
    with caplog.at_level(logging.INFO):
        structured_log.emit("created", "arn:1", ref="OPS-1")
    record = json.loads(caplog.records[-1].message)
    assert record == {"status": "created", "eventArn": "arn:1", "ref": "OPS-1"}
