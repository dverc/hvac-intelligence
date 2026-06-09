from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.constants import SEED_ORG_ID
from app.models.call_transcript import CallTranscript
from app.models.dispatch_job import DispatchJob


@pytest.mark.asyncio
async def test_call_analytics_returns_200_with_correct_structure(
    auth_client,
    seeded_customer,
    db_session,
):
    del seeded_customer
    transcript = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == "call-seed-001")
        )
    ).scalar_one()
    job = (
        await db_session.execute(
            select(DispatchJob).where(DispatchJob.job_number == "DX-SEED-001")
        )
    ).scalar_one()
    transcript.dispatch_job_id = job.job_id
    await db_session.flush()

    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": str(SEED_ORG_ID), "days": 30},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "summary",
        "revenue_impact",
        "calls_by_day",
        "calls_by_hour",
        "top_issue_types",
        "sentiment_breakdown",
    }
    assert body["summary"]["total_calls"] >= 1
    assert body["summary"]["calls_booked"] >= 1
    assert body["summary"]["calls_escalated"] >= 1
    assert isinstance(body["summary"]["booking_rate"], float)
    assert len(body["calls_by_day"]) == 30
    assert len(body["calls_by_hour"]) == 24
    assert body["top_issue_types"][0]["issue_type"] == "AC_FAILURE"
    assert body["sentiment_breakdown"]["negative"] >= 1


@pytest.mark.asyncio
async def test_call_analytics_returns_zero_values_when_org_has_no_calls(auth_client):
    empty_org_id = "00000000-0000-4000-8000-000000000099"
    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": empty_org_id, "days": 7},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_calls"] == 0
    assert body["summary"]["calls_booked"] == 0
    assert body["summary"]["calls_escalated"] == 0
    assert body["summary"]["avg_duration_seconds"] == 0.0
    assert body["summary"]["total_cost_usd"] == 0.0
    assert body["sentiment_breakdown"] == {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
    }


@pytest.mark.asyncio
async def test_call_analytics_booking_rate_zero_when_no_calls(auth_client):
    empty_org_id = "00000000-0000-4000-8000-000000000099"
    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": empty_org_id, "days": 30},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["booking_rate"] == 0.0


@pytest.mark.asyncio
async def test_call_analytics_calls_by_day_has_one_entry_per_day_in_range(auth_client):
    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": str(SEED_ORG_ID), "days": 14},
    )

    assert response.status_code == 200
    calls_by_day = response.json()["calls_by_day"]
    assert len(calls_by_day) == 14
    dates = [entry["date"] for entry in calls_by_day]
    assert len(set(dates)) == 14
    assert all(isinstance(entry["count"], int) for entry in calls_by_day)


@pytest.mark.asyncio
async def test_call_analytics_calls_by_hour_always_has_24_entries(auth_client):
    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": str(SEED_ORG_ID), "days": 30},
    )

    assert response.status_code == 200
    calls_by_hour = response.json()["calls_by_hour"]
    assert len(calls_by_hour) == 24
    assert [entry["hour"] for entry in calls_by_hour] == list(range(24))
    assert all(isinstance(entry["count"], int) for entry in calls_by_hour)


@pytest.mark.asyncio
async def test_call_analytics_includes_revenue_impact_with_roi_multiplier(
    auth_client,
    seeded_customer,
    db_session,
):
    del seeded_customer
    transcript = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == "call-seed-001")
        )
    ).scalar_one()
    job = (
        await db_session.execute(
            select(DispatchJob).where(DispatchJob.job_number == "DX-SEED-001")
        )
    ).scalar_one()
    transcript.dispatch_job_id = job.job_id
    transcript.call_cost_usd = 1.16
    await db_session.flush()

    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": str(SEED_ORG_ID), "days": 30},
    )

    assert response.status_code == 200
    revenue = response.json()["revenue_impact"]
    assert "roi_multiplier" in revenue
    assert revenue["estimated_bookings_value_usd"] == pytest.approx(
        response.json()["summary"]["calls_booked"] * 150.0
    )
    assert revenue["ai_cost_usd"] == pytest.approx(
        response.json()["summary"]["total_cost_usd"]
    )
    assert isinstance(revenue["roi_multiplier"], float)


@pytest.mark.asyncio
async def test_call_analytics_calls_abandoned_counts_short_calls(
    auth_client,
    db_session,
    seeded_customer,
):
    del seeded_customer
    transcript = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == "call-seed-001")
        )
    ).scalar_one()
    transcript.duration_seconds = 20
    await db_session.flush()

    response = await auth_client.get(
        "/api/v1/analytics/calls",
        params={"org_id": str(SEED_ORG_ID), "days": 30},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["calls_abandoned"] == 1
