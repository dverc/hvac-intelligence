import json

from app.services.vapi_payload import (
    extract_call_timing,
    extract_customer_id_from_tool_results,
    extract_phone_from_vapi_payload,
)


def test_extract_phone_from_message_level_customer():
    payload = {
        "customer": {"number": "+19493313190"},
        "call": {"id": "call-1"},
    }
    assert extract_phone_from_vapi_payload(payload) == "+19493313190"


def test_extract_phone_from_variable_values():
    payload = {
        "call": {
            "id": "call-2",
            "assistantOverrides": {
                "variableValues": {"caller_phone": "+15551234567"},
            },
        }
    }
    assert extract_phone_from_vapi_payload(payload) == "+15551234567"


def test_extract_call_timing_from_duration_seconds():
    payload = {
        "startedAt": "2026-06-04T20:27:28Z",
        "durationSeconds": 142,
        "call": {"id": "call-3"},
    }
    started, ended, duration = extract_call_timing(payload)
    assert duration == 142
    assert ended is not None
    assert int((ended - started).total_seconds()) == 142


def test_extract_customer_id_from_create_customer_tool_result():
    payload = {
        "artifact": {
            "messages": [
                {
                    "name": "create_customer",
                    "result": json.dumps(
                        {"status": "created", "customer_id": "18ea568c-5db5-4a41-ab1d-18314a9d54e4"}
                    ),
                }
            ]
        }
    }
    assert (
        extract_customer_id_from_tool_results(payload)
        == "18ea568c-5db5-4a41-ab1d-18314a9d54e4"
    )
