from __future__ import annotations

import json
import logging

_log = logging.getLogger()
_log.setLevel(logging.INFO)


def emit(status: str, event_arn: str, **extra: object) -> None:
    _log.info(json.dumps({"status": status, "eventArn": event_arn, **extra}))
