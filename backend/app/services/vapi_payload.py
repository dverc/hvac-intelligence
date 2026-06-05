"""Shared helpers for parsing Vapi webhook / end-of-call-report payloads."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def extract_phone_from_vapi_payload(payload: dict[str, Any]) -> Optional[str]:
    """Extract caller phone from message or nested call object (Vapi shape variants)."""
    if number := (payload.get("customer") or {}).get("number"):
        return str(number)

    call = payload.get("call") or {}
    if number := (call.get("customer") or {}).get("number"):
        return str(number)

    for container in (payload, call):
        variable_values = container.get("variableValues") or container.get("variable_values") or {}
        if phone := variable_values.get("caller_phone"):
            return str(phone)
        assistant_overrides = container.get("assistantOverrides") or {}
        nested_values = assistant_overrides.get("variableValues") or {}
        if phone := nested_values.get("caller_phone"):
            return str(phone)

    for container in (call, payload):
        phone_number = (
            container.get("phoneNumber")
            or container.get("phone_number")
        )
        if isinstance(phone_number, dict):
            if number := phone_number.get("number"):
                return str(number)
        elif isinstance(phone_number, str):
            return phone_number

    return None


def extract_customer_id_from_tool_results(payload: dict[str, Any]) -> Optional[str]:
    """Return customer_id from a successful create_customer tool result, if present."""
    candidates: list[Any] = []
    artifact = payload.get("artifact") or {}
    for source in (
        artifact.get("messages"),
        payload.get("messages"),
        payload.get("toolCalls"),
        payload.get("toolCallList"),
        artifact.get("toolCalls"),
    ):
        if isinstance(source, list):
            candidates.extend(source)

    for item in candidates:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        if not name:
            function = item.get("function") or {}
            if isinstance(function, dict):
                name = function.get("name")

        if name != "create_customer":
            continue

        result = item.get("result") or item.get("output") or item.get("content")
        customer_id = _parse_customer_id_from_tool_result(result)
        if customer_id:
            return customer_id

    return None


def extract_call_timing(
    payload: dict[str, Any],
) -> tuple[datetime, Optional[datetime], Optional[int]]:
    """Return (start, end, duration_seconds) from Vapi call / message fields."""
    call = payload.get("call") or {}
    now = datetime.now(timezone.utc)

    started_raw = _first_present(
        payload,
        call,
        keys=("startedAt", "startTime", "createdAt", "start_time"),
    )
    ended_raw = _first_present(
        payload,
        call,
        keys=("endedAt", "endTime", "end_time"),
    )
    duration_raw = _first_present(
        payload,
        call,
        keys=("durationSeconds", "duration_seconds", "duration"),
    )

    start_dt = _parse_timestamp(started_raw) or now
    end_dt = _parse_timestamp(ended_raw)

    duration_seconds: Optional[int] = None
    if duration_raw is not None:
        try:
            duration_seconds = int(float(duration_raw))
        except (TypeError, ValueError):
            duration_seconds = None

    if end_dt is None and duration_seconds is not None:
        end_dt = start_dt + timedelta(seconds=duration_seconds)
    elif end_dt is not None and duration_seconds is None:
        duration_seconds = max(int((end_dt - start_dt).total_seconds()), 0)

    return start_dt, end_dt, duration_seconds


def _first_present(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        for key in keys:
            if key in source and source[key] is not None:
                return source[key]
    return None


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # Vapi may send epoch ms or seconds; values above 1e12 are ms.
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.debug("Could not parse timestamp string: %s", value)
            return None
    return None


def _parse_customer_id_from_tool_result(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        customer_id = result.get("customer_id")
        return str(customer_id) if customer_id else None

    if not isinstance(result, str):
        return None

    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    customer_id = parsed.get("customer_id")
    return str(customer_id) if customer_id else None
