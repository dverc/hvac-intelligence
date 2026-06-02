import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.dispatch_job import DispatchJob
from app.models.support_ticket import SupportTicket
from app.rag.retriever import RAGRetriever
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.ticket_service import TicketService
from app.services.tool_executor import ToolExecutor


@pytest.fixture
def tool_executor(db_session, mock_rag_retriever):
    return ToolExecutor(
        customer_service=CustomerService(db_session),
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=mock_rag_retriever,
    )


@pytest.mark.asyncio
async def test_execute_batch_parses_nested_function_tool_call(
    tool_executor, seeded_customer
):
    tool_call_list = [
        {
            "id": "tc-nested",
            "type": "function",
            "function": {
                "name": "query_churn_score",
                "arguments": {"customer_id": seeded_customer["customer_id"]},
            },
        }
    ]
    results = await tool_executor.execute_batch(tool_call_list)
    assert results[0]["toolCallId"] == "tc-nested"
    payload = json.loads(results[0]["result"])
    assert "churn_probability" in payload
    assert payload["risk_tier"] == "HIGH"


@pytest.mark.asyncio
async def test_execute_batch_parses_stringified_function_arguments(
    tool_executor, seeded_customer
):
    tool_call_list = [
        {
            "id": "tc-string-args",
            "type": "function",
            "function": {
                "name": "query_churn_score",
                "arguments": json.dumps({"customer_id": seeded_customer["customer_id"]}),
            },
        }
    ]
    results = await tool_executor.execute_batch(tool_call_list)
    payload = json.loads(results[0]["result"])
    assert payload["risk_tier"] == "HIGH"


@pytest.mark.asyncio
async def test_schedule_dispatch_creates_job(tool_executor, seeded_customer, db_session):
    customer_id = seeded_customer["customer_id"]
    result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P1",
            preferred_window="tomorrow_AM",
            issue_description="Unit not cooling",
        )
    )
    assert result["job_number"]

    row = await db_session.execute(
        select(DispatchJob).where(DispatchJob.customer_id == uuid.UUID(customer_id))
    )
    job = row.scalars().first()
    assert job is not None
    assert job.priority == "P1"


@pytest.mark.asyncio
async def test_query_churn_score_rejects_unresolved_template_customer_id(tool_executor):
    result = json.loads(
        await tool_executor.execute_query_churn_score(customer_id="{{customer_id}}")
    )
    assert "error" in result
    assert "get_customer_info" in result["error"]


@pytest.mark.asyncio
async def test_create_support_ticket_rejects_missing_required_fields(tool_executor):
    result = json.loads(await tool_executor.execute_create_ticket())
    assert result["error"] == (
        "Missing required fields. Please collect customer_id, ticket_type, "
        "subject, description, and priority before calling this tool."
    )


@pytest.mark.asyncio
async def test_query_churn_score_schema(tool_executor, seeded_customer):
    result = json.loads(
        await tool_executor.execute_query_churn_score(
            customer_id=seeded_customer["customer_id"]
        )
    )
    assert "churn_probability" in result
    assert "risk_tier" in result
    assert result["risk_tier"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@pytest.mark.asyncio
async def test_get_customer_info_returns_profile(tool_executor, seeded_customer):
    result = json.loads(
        await tool_executor.execute_get_customer_info(
            lookup_method="phone",
            lookup_value=seeded_customer["phone"],
        )
    )
    assert result["found"] is True
    assert result["equipment"]
    assert "open_tickets" in result


@pytest.mark.asyncio
async def test_rag_knowledge_query_calls_retriever(tool_executor, seeded_customer):
    mock_retriever = AsyncMock(spec=RAGRetriever)
    mock_retriever.retrieve.return_value = [{"chunk_id": "c1", "text": "FAQ"}]
    tool_executor.rag_retriever = mock_retriever

    await tool_executor.execute_rag_query(
        query="What is the warranty on a Carrier AC?",
        namespace="faq_general",
        top_k=3,
    )
    mock_retriever.retrieve.assert_awaited_once_with(
        query="What is the warranty on a Carrier AC?",
        namespace="faq_general",
        top_k=3,
        filter_model=None,
    )


@pytest.mark.asyncio
async def test_create_support_ticket_persists(tool_executor, seeded_customer, db_session):
    customer_id = seeded_customer["customer_id"]
    result = json.loads(
        await tool_executor.execute_create_ticket(
            customer_id=customer_id,
            ticket_type="COMPLAINT_ESCALATION",
            subject="AC still broken",
            description="Third recurrence",
            priority="P2",
        )
    )
    assert result["success"] is True

    row = await db_session.execute(
        select(SupportTicket).where(
            SupportTicket.customer_id == uuid.UUID(customer_id)
        )
    )
    tickets = row.scalars().all()
    assert any(t.subject == "AC still broken" for t in tickets)


@pytest.mark.asyncio
async def test_get_equipment_info_returns_view_data(
    tool_executor, seeded_customer
):
    result = json.loads(
        await tool_executor.execute_get_equipment_info(
            customer_id=seeded_customer["customer_id"]
        )
    )
    assert result["found"] is True
    assert len(result["equipment"]) >= 1
    assert result["equipment"][0].get("make") == "Carrier"
