"""End-to-end booking: schedule_dispatch → DB job → SMS (mocked Twilio)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.dispatch_job import DispatchJob
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.ticket_service import TicketService
from app.services.tool_executor import ToolExecutor


@pytest.fixture
def booking_executor(db_session, mock_rag_retriever):
    from app.core.constants import SEED_ORG_ID

    executor = ToolExecutor(
        customer_service=CustomerService(db_session),
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=mock_rag_retriever,
    )
    executor.set_tenant(SEED_ORG_ID, org_slug="hvac-demo")
    return executor


@pytest.mark.asyncio
async def test_schedule_dispatch_creates_job_and_sends_sms(
    booking_executor, seeded_customer, db_session
):
    customer_id = seeded_customer["customer_id"]

    mock_messages = MagicMock()
    mock_messages.create.return_value = MagicMock(sid="SM-E2E-001")
    mock_twilio = MagicMock()
    mock_twilio.messages = mock_messages

    with (
        patch("app.services.sms_service.get_settings") as mock_settings,
        patch("twilio.rest.Client", return_value=mock_twilio),
    ):
        mock_settings.return_value.TWILIO_ACCOUNT_SID = "test_sid"
        mock_settings.return_value.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.return_value.TWILIO_FROM_NUMBER = "+15550001111"

        result = json.loads(
            await booking_executor.execute_schedule_dispatch(
                customer_id=customer_id,
                issue_type="AC_FAILURE",
                priority="P3",
                preferred_window="monday afternoon",
                issue_description="E2E booking test",
            )
        )

    assert result.get("success") is True, result
    job_id = result.get("job_id")
    assert job_id

    job = await db_session.get(DispatchJob, uuid.UUID(job_id))
    assert job is not None
    assert job.scheduled_window_start is not None
    assert job.scheduled_window_end is not None

    mock_messages.create.assert_called_once()
    call_kwargs = mock_messages.create.call_args.kwargs
    assert call_kwargs["to"].startswith("+1")
