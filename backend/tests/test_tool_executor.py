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
    from app.core.constants import SEED_ORG_ID

    executor = ToolExecutor(
        customer_service=CustomerService(db_session),
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=mock_rag_retriever,
    )
    # Tenant must be set before handlers run (mirrors webhook resolution).
    executor.set_tenant(SEED_ORG_ID)
    return executor


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


@pytest.mark.asyncio
async def test_create_customer_success(tool_executor, db_session):
    phone = "+15559998877"
    result = json.loads(
        await tool_executor.execute_create_customer(
            full_name="Jane Newcaller",
            phone_primary=phone,
            service_address_line1="123 Main St",
            service_address_city="Irvine",
            service_address_state="CA",
            service_address_zip="92618",
            email="jane@example.com",
        )
    )
    assert result["status"] == "created"
    assert result["customer_id"]
    assert "Jane Newcaller" in result["message"]

    from app.models.customer import Customer

    row = await db_session.execute(
        select(Customer).where(Customer.phone_primary == phone)
    )
    customer = row.scalar_one_or_none()
    assert customer is not None
    assert customer.full_name == "Jane Newcaller"
    assert customer.external_id.startswith("VOICE-")


@pytest.mark.asyncio
async def test_create_customer_duplicate_phone_returns_error(
    tool_executor, seeded_customer
):
    result = json.loads(
        await tool_executor.execute_create_customer(
            full_name="Duplicate Test",
            phone_primary=seeded_customer["phone"],
            service_address_line1="456 Oak Ave",
            service_address_city="Irvine",
            service_address_state="CA",
            service_address_zip="92618",
        )
    )
    assert "error" in result
    assert "already exists" in result["error"]


@pytest.mark.asyncio
async def test_update_customer_updates_address(tool_executor, seeded_customer, db_session):
    customer_id = seeded_customer["customer_id"]
    result = json.loads(
        await tool_executor.execute_update_customer(
            customer_id=customer_id,
            service_address_line1="165 Deeley St",
            service_address_city="Irvine",
            service_address_state="CA",
            service_address_zip="92614",
        )
    )
    assert result["status"] == "updated"
    assert "service_address_line1" in result["updated_fields"]

    from app.models.customer import Customer

    customer = await db_session.get(Customer, uuid.UUID(customer_id))
    assert customer.address_line1 == "165 Deeley St"
    assert customer.city == "Irvine"


@pytest.mark.asyncio
async def test_update_customer_empty_args_returns_validation_error(tool_executor, seeded_customer):
    result = json.loads(
        await tool_executor.execute_update_customer(
            customer_id=seeded_customer["customer_id"],
        )
    )
    assert "error" in result
    assert "at least one field" in result["error"].lower()


@pytest.mark.asyncio
async def test_create_equipment_success(tool_executor, seeded_customer, db_session):
    customer_id = seeded_customer["customer_id"]
    result = json.loads(
        await tool_executor.execute_create_equipment(
            customer_id=customer_id,
            equipment_type="FURNACE",
            make="Lennox",
            model="SL280V",
            install_year=2019,
        )
    )
    assert result["status"] == "created"
    assert result["equipment_id"]

    from app.models.equipment import Equipment

    row = await db_session.execute(
        select(Equipment).where(Equipment.customer_id == uuid.UUID(customer_id))
    )
    units = row.scalars().all()
    assert any(e.make == "Lennox" and e.model == "SL280V" for e in units)


@pytest.mark.asyncio
async def test_update_dispatch_address_correction_appended_to_notes(
    tool_executor, seeded_customer, db_session
):
    dispatch_result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window="tomorrow afternoon",
            issue_description="Unit not cooling",
        )
    )
    job_id = dispatch_result["job_id"]

    result = json.loads(
        await tool_executor.execute_update_dispatch(
            job_id=job_id,
            service_address_override="165 Deeley, Irvine CA",
        )
    )
    assert result["status"] == "updated"

    job = await db_session.get(DispatchJob, uuid.UUID(job_id))
    assert "ADDRESS CORRECTION: 165 Deeley, Irvine CA" in (job.issue_description or "")


@pytest.mark.asyncio
async def test_update_dispatch_cancel_sets_status_cancelled(
    tool_executor, seeded_customer, db_session
):
    dispatch_result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P3",
            preferred_window="tomorrow",
            issue_description="No longer needed",
        )
    )
    job_id = dispatch_result["job_id"]

    result = json.loads(
        await tool_executor.execute_update_dispatch(job_id=job_id, cancel=True)
    )
    assert result["status"] == "updated"

    job = await db_session.get(DispatchJob, uuid.UUID(job_id))
    assert job.job_status == "CANCELLED"


@pytest.mark.asyncio
async def test_lookup_service_info_by_service_code(tool_executor, db_session):
    from app.schemas.service_catalog import ServiceCatalogCreate
    from app.services.service_catalog_service import ServiceCatalogService

    catalog = ServiceCatalogService(db_session)
    await catalog.create(
        tool_executor.org_id,
        ServiceCatalogCreate(
            service_code="TOOL_LOOKUP",
            service_name="Tool Lookup Test",
            category="diagnostic",
            base_price_usd=89,
            price_max_usd=129,
            duration_minutes_min=45,
            duration_minutes_max=60,
        ),
    )
    await db_session.commit()

    result = json.loads(
        await tool_executor.execute_lookup_service_info(service_code="TOOL_LOOKUP")
    )
    assert result["services_found"] == 1
    assert result["results"][0]["price_range"] == "$89 - $129"


@pytest.mark.asyncio
async def test_lookup_service_info_no_results_helpful_message(tool_executor):
    result = json.loads(
        await tool_executor.execute_lookup_service_info(
            service_code="NONEXISTENT_SERVICE_XYZ"
        )
    )
    assert result["services_found"] == 0
    assert "technician" in result["message"].lower()


@pytest.mark.asyncio
async def test_lookup_service_info_validation_error_without_args(tool_executor):
    result = json.loads(await tool_executor.execute_lookup_service_info())
    assert "error" in result
