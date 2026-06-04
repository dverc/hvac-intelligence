from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.constants import SEED_ORG_ID
from app.core.encryption import encrypt_token
from app.models.google_calendar_token import GoogleCalendarToken
from app.rag.retriever import RAGRetriever
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.ticket_service import TicketService
from app.services.tool_executor import ToolExecutor


@pytest.fixture
def tool_executor(db_session, mock_rag_retriever):
    executor = ToolExecutor(
        customer_service=CustomerService(db_session),
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=mock_rag_retriever,
    )
    executor.set_tenant(SEED_ORG_ID, org_slug="hvac-demo")
    return executor


@pytest.fixture
def encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_create_job_attempts_calendar_event(
    db_session, seeded_customer, encryption_key
):
    token = GoogleCalendarToken(
        org_id=SEED_ORG_ID,
        technician_id=uuid.UUID(seeded_customer["technician_id"]),
        google_account_email="owner@example.com",
        calendar_id="primary",
        access_token=encrypt_token("access") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    with patch(
        "app.services.google_calendar_service.GoogleCalendarService.create_calendar_event",
        new_callable=AsyncMock,
        return_value="google-evt-1",
    ) as mock_create:
        svc = DispatchService(db_session)
        result = await svc.create_job(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window="tomorrow morning",
            issue_description="Warm air",
            org_id=SEED_ORG_ID,
        )

    assert result["success"] is True
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_job_succeeds_when_calendar_fails(
    db_session, seeded_customer, encryption_key
):
    token = GoogleCalendarToken(
        org_id=SEED_ORG_ID,
        google_account_email="owner@example.com",
        calendar_id="primary",
        access_token=encrypt_token("access") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    with patch(
        "app.services.google_calendar_service.GoogleCalendarService.create_calendar_event",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Google API down"),
    ):
        svc = DispatchService(db_session)
        result = await svc.create_job(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P3",
            preferred_window="tomorrow afternoon",
            issue_description="Noise",
            org_id=SEED_ORG_ID,
        )

    assert result["success"] is True
    assert result.get("job_number")


@pytest.mark.asyncio
async def test_cancelled_job_calls_delete_calendar_event(
    db_session, seeded_customer, encryption_key, tool_executor
):
    from app.models.dispatch_job import DispatchJob
    from app.schemas.tools import UpdateDispatchArgs

    create_result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P3",
            preferred_window="tomorrow evening",
            issue_description="Evening slot",
        )
    )
    assert create_result.get("success") is True
    job_id = create_result["job_id"]

    job = await db_session.get(DispatchJob, uuid.UUID(job_id))
    job.google_calendar_event_id = "gcal-event-to-delete"
    await db_session.flush()

    with patch(
        "app.services.google_calendar_service.GoogleCalendarService.delete_calendar_event",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_delete:
        svc = DispatchService(db_session)
        result = await svc.update_job(
            UpdateDispatchArgs(job_id=job_id, cancel=True),
            SEED_ORG_ID,
        )

    assert result["success"] is True
    mock_delete.assert_called_once_with(SEED_ORG_ID, "gcal-event-to-delete")
