"""Tests for transcript list and call detail API endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.call_transcript import CallTranscript


@pytest.mark.asyncio
async def test_get_customer_transcripts_returns_full_fields(
    api_client,
    seeded_customer,
    db_session,
):
    transcript = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == "call-seed-001")
        )
    ).scalar_one()
    transcript.recording_url = "https://example.com/recording.mp3"
    transcript.transcript_raw = "Agent: Hello\nCustomer: My AC stopped working"
    transcript.transcript_json = [
        {"role": "assistant", "message": "Hello"},
        {"role": "user", "message": "My AC stopped working"},
    ]
    transcript.vapi_end_reason = "customer-ended-call"
    transcript.call_cost_usd = Decimal("0.4200")
    transcript.call_summary = "Customer requested AC repair dispatch"
    transcript.tool_calls_log = [{"name": "schedule_dispatch", "result": "ok"}]
    await db_session.flush()

    response = await api_client.get(
        f"/api/v1/customers/{seeded_customer['customer_id']}/transcripts"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == seeded_customer["customer_id"]
    assert len(body["transcripts"]) >= 1

    item = next(t for t in body["transcripts"] if t["call_id"] == "call-seed-001")
    assert item["transcript_id"] == seeded_customer["transcript_id"]
    assert item["call_start_utc"] is not None
    assert item["call_end_utc"] is not None
    assert item["duration_seconds"] == 480
    assert item["call_outcome"] == "DISPATCHED"
    assert item["vapi_end_reason"] == "customer-ended-call"
    assert item["call_cost_usd"] == pytest.approx(0.42)
    assert item["recording_url"] == "https://example.com/recording.mp3"
    assert item["call_summary"] == "Customer requested AC repair dispatch"
    assert item["sentiment_overall"] == pytest.approx(-0.55)
    assert item["sentiment_score"] == pytest.approx(-0.55)
    assert "My AC stopped working" in item["transcript_raw"]
    assert len(item["transcript_json"]) == 2
    assert item["tool_calls_log"][0]["name"] == "schedule_dispatch"
    assert item["churn_risk_at_call_start"] == pytest.approx(0.78)
    assert item["intervention_successful"] is True


@pytest.mark.asyncio
async def test_get_call_detail_returns_200(
    api_client,
    seeded_customer,
    db_session,
):
    transcript = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == "call-seed-001")
        )
    ).scalar_one()
    transcript.recording_url = "https://example.com/recording.mp3"
    transcript.transcript_raw = "Full transcript text"
    transcript.transcript_json = [{"role": "user", "message": "Help"}]
    transcript.vapi_end_reason = "assistant-ended-call"
    transcript.call_cost_usd = Decimal("1.2500")
    transcript.call_summary = "Resolved FAQ"
    await db_session.flush()

    response = await api_client.get("/api/v1/calls/call-seed-001")

    assert response.status_code == 200
    body = response.json()
    assert body["call_id"] == "call-seed-001"
    assert body["transcript_id"] == seeded_customer["transcript_id"]
    assert body["recording_url"] == "https://example.com/recording.mp3"
    assert body["transcript_raw"] == "Full transcript text"
    assert body["call_summary"] == "Resolved FAQ"
    assert body["vapi_end_reason"] == "assistant-ended-call"
    assert body["call_cost_usd"] == pytest.approx(1.25)
    assert body["duration_seconds"] == 480
    assert body["call_outcome"] == "DISPATCHED"


@pytest.mark.asyncio
async def test_get_call_detail_returns_404_for_unknown_call_id(api_client):
    response = await api_client.get("/api/v1/calls/nonexistent-call-id")

    assert response.status_code == 404
    assert "nonexistent-call-id" in response.json()["detail"]
