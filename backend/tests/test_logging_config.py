from __future__ import annotations

import asyncio
import logging

import pytest

from app.core.logging_config import (
    CallIdFilter,
    call_id_var,
    get_call_id,
    set_call_id,
)


def test_set_call_id_and_get_call_id_round_trip():
    set_call_id("call-abc-123")
    try:
        assert get_call_id() == "call-abc-123"
    finally:
        set_call_id("")


def test_call_id_defaults_to_empty_string():
    token = call_id_var.set("")
    try:
        assert get_call_id() == ""
    finally:
        call_id_var.reset(token)


def test_call_id_filter_adds_call_id_to_record():
    set_call_id("filter-test-call")
    try:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        flt = CallIdFilter()
        assert flt.filter(record) is True
        assert record.call_id == "filter-test-call"
    finally:
        set_call_id("")


@pytest.mark.asyncio
async def test_call_id_context_isolation_across_async_tasks():
    results: dict[str, str] = {}

    async def worker(key: str, call_id: str) -> None:
        set_call_id(call_id)
        await asyncio.sleep(0.01)
        results[key] = get_call_id()

    await asyncio.gather(
        worker("task_a", "call-a"),
        worker("task_b", "call-b"),
    )

    assert results["task_a"] == "call-a"
    assert results["task_b"] == "call-b"
