import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.dispatch_job import DispatchJob
from app.models.support_ticket import SupportTicket
from app.rag.retriever import RAGRetriever
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.ticket_service import TicketService
from app.services.tool_executor import ToolExecutor


@pytest_asyncio.fixture
async def marcus_and_elena_technicians(db_session):
    """Marcus (highest rating) and Elena for preferred-window name routing tests."""
    from app.core.constants import SEED_ORG_ID
    from app.models.technician import Technician
    from app.models.technician_schedule import TechnicianSchedule

    marcus = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-MARCUS-{uuid.uuid4().hex[:8]}",
        full_name="Marcus Thompson",
        phone="+15551234001",
        hire_date=date(2016, 4, 12),
        tenure_years=Decimal("9"),
        avg_customer_rating=Decimal("4.82"),
        skills=["hvac"],
    )
    elena = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-ELENA-{uuid.uuid4().hex[:8]}",
        full_name="Elena Vasquez",
        phone="+15551234002",
        hire_date=date(2021, 9, 1),
        tenure_years=Decimal("4"),
        avg_customer_rating=Decimal("4.65"),
        skills=["hvac"],
    )
    db_session.add_all([marcus, elena])
    await db_session.flush()

    for tech in (marcus, elena):
        for dow in range(5):
            db_session.add(
                TechnicianSchedule(
                    org_id=SEED_ORG_ID,
                    technician_id=tech.technician_id,
                    day_of_week=dow,
                    start_time=datetime.strptime("08:00", "%H:%M").time(),
                    end_time=datetime.strptime("17:00", "%H:%M").time(),
                    is_active=True,
                    effective_from=date.today(),
                )
            )
    await db_session.flush()
    return {"marcus": marcus, "elena": elena}


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
    executor.set_tenant(SEED_ORG_ID, org_slug="hvac-demo")
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
async def test_schedule_dispatch_picks_elena_when_name_in_preferred_window(
    tool_executor, seeded_customer, marcus_and_elena_technicians, db_session
):
    elena = marcus_and_elena_technicians["elena"]
    result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window="Tomorrow Monday June 8 10 AM to 12 PM with Elena",
            issue_description="Unit not cooling",
        )
    )
    assert result.get("success") is True, result
    assert result["technician"]["name"].startswith("Elena")

    job = await db_session.get(DispatchJob, uuid.UUID(result["job_id"]))
    assert job.technician_id == elena.technician_id


@pytest.mark.asyncio
async def test_schedule_dispatch_falls_back_when_named_technician_unavailable(
    tool_executor, seeded_customer, marcus_and_elena_technicians, db_session
):
    elena = marcus_and_elena_technicians["elena"]
    marcus = marcus_and_elena_technicians["marcus"]
    window = "monday morning with Elena"
    customer_id = seeded_customer["customer_id"]

    first = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window=window,
            issue_description="First booking for Elena",
        )
    )
    assert first.get("success") is True, first
    assert first["technician"]["name"].startswith("Elena")

    second = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window=window,
            issue_description="Fallback booking",
        )
    )
    assert second.get("success") is True, second
    assert second["technician"]["name"].startswith("Marcus")

    job = await db_session.get(DispatchJob, uuid.UUID(second["job_id"]))
    assert job.technician_id == marcus.technician_id
    assert job.technician_id != elena.technician_id


@pytest.mark.asyncio
async def test_schedule_dispatch_creates_job(tool_executor, seeded_customer, db_session):
    customer_id = seeded_customer["customer_id"]
    result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=customer_id,
            issue_type="AC_FAILURE",
            priority="P1",
            preferred_window="monday morning",
            issue_description="Unit not cooling",
        )
    )
    assert result.get("success") is True, result
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
        namespace="hvac-demo::faq_general",
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
            preferred_window="monday afternoon",
            issue_description="Unit not cooling",
        )
    )
    assert dispatch_result.get("success") is True, dispatch_result
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
async def test_update_dispatch_cancel_creates_approval_ticket_not_immediate_cancel(
    tool_executor, seeded_customer, db_session
):
    dispatch_result = json.loads(
        await tool_executor.execute_schedule_dispatch(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P3",
            preferred_window="tuesday morning",
            issue_description="No longer needed",
        )
    )
    assert dispatch_result.get("success") is True, dispatch_result
    job_id = dispatch_result["job_id"]

    result = json.loads(
        await tool_executor.execute_update_dispatch(
            job_id=job_id,
            cancel=True,
            notes="Customer traveling out of town",
        )
    )
    assert result["status"] == "pending_approval"
    assert "cancellation request" in result["message"].lower()
    assert "team member" in result["message"].lower()

    job = await db_session.get(DispatchJob, uuid.UUID(job_id))
    assert job is not None
    assert job.job_status != "CANCELLED"

    ticket_row = await db_session.execute(
        select(SupportTicket).where(
            SupportTicket.customer_id == uuid.UUID(seeded_customer["customer_id"]),
            SupportTicket.ticket_type == "MANAGER_CALLBACK",
            SupportTicket.subject == "Cancellation Request — Pending Approval",
        )
    )
    ticket = ticket_row.scalars().first()
    assert ticket is not None
    assert job.job_number in ticket.description
    assert "Customer traveling out of town" in ticket.description
    assert ticket.priority == "P1"


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


@pytest.mark.asyncio
async def test_transfer_call_returns_destination_when_phone_set(
    tool_executor, db_session
):
    from app.core.constants import SEED_ORG_ID
    from app.models.organization import Organization

    org = await db_session.get(Organization, SEED_ORG_ID)
    org.transfer_phone_number = "+19491234567"
    await db_session.flush()

    result = await tool_executor.execute_transfer_call(
        reason="Customer requested human agent"
    )

    assert isinstance(result, dict)
    assert "destination" in result
    assert result["destination"]["type"] == "number"
    assert result["destination"]["number"] == "+19491234567"


@pytest.mark.asyncio
async def test_transfer_call_returns_fallback_when_no_phone_set(
    tool_executor, db_session
):
    from app.core.constants import SEED_ORG_ID
    from app.models.organization import Organization

    org = await db_session.get(Organization, SEED_ORG_ID)
    org.transfer_phone_number = None
    await db_session.flush()

    result = await tool_executor.execute_transfer_call()

    assert isinstance(result, str)
    assert not isinstance(result, dict)
    assert "callback" in result.lower()
