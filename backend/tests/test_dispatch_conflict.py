import json
import uuid

import pytest
from sqlalchemy import func, select

from app.models.dispatch_job import DispatchJob
from app.rag.retriever import RAGRetriever
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.ticket_service import TicketService
from app.services.tool_executor import ToolExecutor


@pytest.fixture
def tool_executor(db_session, mock_rag_retriever):
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
async def test_schedule_dispatch_rejects_double_booking(tool_executor, seeded_customer):
    customer_id = seeded_customer["customer_id"]
    window = "tomorrow morning"

    first = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window=window,
            issue_description="First booking",
        )
    )
    assert first.get("success") is True, first

    second = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window=window,
            issue_description="Duplicate booking",
        )
    )
    assert second.get("success") is False
    assert second.get("error") == "conflict"


@pytest.mark.asyncio
async def test_schedule_dispatch_succeeds_when_free(tool_executor, seeded_customer):
    result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P3",
            preferred_window="tomorrow afternoon",
            issue_description="Afternoon slot",
        )
    )
    assert result.get("success") is True
    assert result.get("job_number")


@pytest.mark.asyncio
async def test_sequential_non_overlapping_bookings_succeed(
    tool_executor, seeded_customer, db_session
):
    customer_id = seeded_customer["customer_id"]

    morning = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P3",
            preferred_window="tomorrow morning",
            issue_description="Morning slot",
        )
    )
    afternoon = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="FURNACE_NO_HEAT",
            priority="P3",
            preferred_window="tomorrow afternoon",
            issue_description="Afternoon slot",
        )
    )
    assert morning.get("success") is True
    assert afternoon.get("success") is True

    job_count = (
        await db_session.execute(
            select(func.count()).select_from(DispatchJob).where(
                DispatchJob.customer_id == uuid.UUID(customer_id),
                DispatchJob.job_status == "SCHEDULED",
            )
        )
    ).scalar_one()
    assert job_count >= 2
