import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.call_transcript import CallTranscript
from app.models.dispatch_job import DispatchJob
from app.services.transcript_service import TranscriptService


@pytest.mark.asyncio
async def test_process_completed_call_extracts_vapi_enrichment_fields(
    db_session, seeded_customer
):
    service = TranscriptService(db_session)
    call_id = f"eocr-{uuid.uuid4().hex[:8]}"
    payload = {
        "type": "end-of-call-report",
        "summary": "Customer scheduled AC repair.",
        "recordingUrl": "https://storage.vapi.ai/recordings/test.wav",
        "endedReason": "customer-ended-call",
        "cost": 0.42,
        "costBreakdown": {"transport": 0.12, "llm": 0.30},
        "assistantId": "4081474b-7087-41e2-bd9a-f251aeede78c",
        "call": {
            "id": call_id,
            "customer": {"number": seeded_customer["phone"]},
            "startedAt": "2026-06-01T12:00:00Z",
            "endedAt": "2026-06-01T12:05:00Z",
        },
        "messages": [
            {"role": "assistant", "message": "Hi, how can I help?"},
            {"role": "user", "message": "My AC is not cooling."},
        ],
    }

    with patch("app.services.transcript_service.publish_call_features", return_value=True):
        result = await service.process_completed_call(payload)
        await db_session.commit()

    assert result is not None
    assert result["call_id"] == call_id
    assert result["customer_id"] == seeded_customer["customer_id"]
    assert result["duration_seconds"] == 300
    assert result["call_cost_usd"] == pytest.approx(0.42)

    row = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )
    ).scalar_one()
    assert row.recording_url == "https://storage.vapi.ai/recordings/test.wav"
    assert row.call_summary == "Customer scheduled AC repair."
    assert row.vapi_end_reason == "customer-ended-call"
    assert row.call_cost_usd == Decimal("0.42")
    assert row.vapi_assistant_id == "4081474b-7087-41e2-bd9a-f251aeede78c"
    assert row.vapi_metadata["cost_breakdown"] == {"transport": 0.12, "llm": 0.30}


@pytest.mark.asyncio
async def test_process_completed_call_links_recent_dispatch_job(
    db_session, seeded_customer
):
    customer_id = uuid.UUID(seeded_customer["customer_id"])
    call_start = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    job = DispatchJob(
        job_number=f"DX-{uuid.uuid4().hex[:4].upper()}",
        customer_id=customer_id,
        issue_type="AC_FAILURE",
        issue_description="No cooling",
        created_at=call_start - timedelta(minutes=30),
    )
    db_session.add(job)
    await db_session.flush()

    service = TranscriptService(db_session)
    call_id = f"eocr-dispatch-{uuid.uuid4().hex[:8]}"
    payload = {
        "type": "end-of-call-report",
        "call": {
            "id": call_id,
            "customer": {"number": seeded_customer["phone"]},
            "startedAt": call_start.isoformat().replace("+00:00", "Z"),
            "endedAt": (call_start + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        },
        "messages": [{"role": "user", "message": "Schedule a visit."}],
    }

    with patch("app.services.transcript_service.publish_call_features", return_value=True):
        await service.process_completed_call(payload)
        await db_session.commit()

    row = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )
    ).scalar_one()
    assert row.dispatch_job_id == job.job_id
