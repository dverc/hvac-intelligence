from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

call_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("call_id", default="")


def set_call_id(call_id: str) -> None:
    call_id_var.set(call_id)


def get_call_id() -> str:
    return call_id_var.get()


class CallIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.call_id = get_call_id()
        return True


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "call_id": getattr(record, "call_id", ""),
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload)


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonLogFormatter())
    handler.addFilter(CallIdFilter())
    root.addHandler(handler)
    root.addFilter(CallIdFilter())
    root.setLevel(logging.INFO)
