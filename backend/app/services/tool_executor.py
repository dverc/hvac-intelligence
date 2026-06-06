from __future__ import annotations

import asyncio
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import observe_tool_execution
from app.rag.constants import get_base_namespace, get_namespace
from app.rag.retriever import RAGRetriever
from app.schemas.customer import CustomerAddressPatch, CustomerUpdate
from app.schemas.organization import OrganizationSettings
from app.schemas.tools import (
    CheckAvailabilityArgs,
    CreateCustomerArgs,
    CreateEquipmentArgs,
    CreateSupportTicketArgs,
    GetCustomerInfoArgs,
    GetEquipmentInfoArgs,
    LookupServiceInfoArgs,
    QueryChurnScoreArgs,
    RagKnowledgeQueryArgs,
    ScheduleDispatchArgs,
    UpdateCustomerArgs,
    UpdateDispatchArgs,
)
from app.services.availability_service import AvailabilityService
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.equipment_service import EquipmentService
from app.services.service_catalog_service import (
    ServiceCatalogService,
    format_duration,
    format_price_range,
)
from app.services.ticket_service import TicketService
from app.services.window_parser import parse_date_range

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, str] = {
    "schedule_dispatch": "execute_schedule_dispatch",
    "query_churn_score": "execute_query_churn_score",
    "get_customer_info": "execute_get_customer_info",
    "get_equipment_info": "execute_get_equipment_info",
    "rag_knowledge_query": "execute_rag_query",
    "create_support_ticket": "execute_create_ticket",
    "create_customer": "execute_create_customer",
    "update_customer": "execute_update_customer",
    "create_equipment": "execute_create_equipment",
    "update_dispatch": "execute_update_dispatch",
    "lookup_service_info": "execute_lookup_service_info",
    "check_availability": "execute_check_availability",
}


def _parse_vapi_tool_call(tool_call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Extract toolCallId, name, and arguments from Vapi tool-call payload variants."""
    tool_call_id = str(tool_call.get("id") or tool_call.get("toolCallId") or "")

    function_block = tool_call.get("function")
    if not isinstance(function_block, dict):
        nested = tool_call.get("toolCall")
        if isinstance(nested, dict):
            function_block = nested.get("function")

    if isinstance(function_block, dict):
        tool_name = str(function_block.get("name") or "")
        raw_args = (
            function_block.get("arguments")
            if function_block.get("arguments") is not None
            else function_block.get("parameters", {})
        )
    else:
        tool_name = str(tool_call.get("name") or "")
        raw_args = tool_call.get("arguments", {})

    if isinstance(raw_args, str):
        args = json.loads(raw_args) if raw_args else {}
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        args = {}

    return tool_call_id, tool_name, args


def _is_unresolved_template(value: Any) -> bool:
    return isinstance(value, str) and value.strip().startswith("{{")


_REDACT_KEYWORDS = ("phone", "number", "mobile", "email", "address", "name", "full_name")


def _redact_args(args: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(args)
    for key in redacted:
        key_lower = key.lower()
        if any(keyword in key_lower for keyword in _REDACT_KEYWORDS):
            redacted[key] = "[REDACTED]"
    return redacted


class ToolExecutor:
    def __init__(
        self,
        customer_service: CustomerService,
        dispatch_service: DispatchService,
        churn_service: ChurnService,
        ticket_service: TicketService,
        rag_retriever: RAGRetriever,
        service_catalog_service: ServiceCatalogService | None = None,
        availability_service: AvailabilityService | None = None,
    ) -> None:
        self.customer_service = customer_service
        self.dispatch_service = dispatch_service
        self.churn_service = churn_service
        self.ticket_service = ticket_service
        self.rag_retriever = rag_retriever
        self.service_catalog_service = service_catalog_service or ServiceCatalogService(
            customer_service.db
        )
        self.availability_service = availability_service or AvailabilityService(
            customer_service.db
        )
        # Tenant context — MUST be set (set_tenant) before any handler runs.
        self.org_id: uuid.UUID | None = None
        self.org_slug: str | None = None
        self.org_settings: OrganizationSettings | None = None

    def set_tenant(
        self,
        org_id: uuid.UUID,
        settings: OrganizationSettings | None = None,
        org_slug: str | None = None,
    ) -> None:
        self.org_id = org_id
        self.org_slug = org_slug
        self.org_settings = settings

    @property
    def db(self) -> AsyncSession:
        return self.customer_service.db

    async def execute_batch(self, tool_call_list: list[dict[str, Any]]) -> list[dict[str, str]]:
        tasks = [self._execute_single(tc) for tc in tool_call_list]
        return await asyncio.gather(*tasks)

    async def _execute_single(self, tool_call: dict[str, Any]) -> dict[str, str]:
        tool_call_id, tool_name, args = _parse_vapi_tool_call(tool_call)
        logger.info(
            "Executing Vapi tool call id=%s name=%s args=%s",
            tool_call_id,
            tool_name,
            _redact_args(args),
        )

        # FAIL CLOSED: never run a tenant-scoped write/read without a resolved org.
        if self.org_id is None:
            return {
                "toolCallId": tool_call_id,
                "result": json.dumps(
                    {"error": "Tenant not resolved for this call; cannot execute tools."}
                ),
            }

        handler_name = TOOL_REGISTRY.get(tool_name)
        if not handler_name:
            return {
                "toolCallId": tool_call_id,
                "result": json.dumps({"error": f"Unknown tool: {tool_name}"}),
            }

        # Enforce per-org enabled_tools server-side (None = all tools enabled).
        if (
            self.org_settings is not None
            and self.org_settings.enabled_tools is not None
            and tool_name not in self.org_settings.enabled_tools
        ):
            return {
                "toolCallId": tool_call_id,
                "result": json.dumps(
                    {"error": f"Tool '{tool_name}' is not enabled for this organization."}
                ),
            }

        try:
            handler = getattr(self, handler_name)
            with observe_tool_execution(tool_name):
                result = await handler(**args)
            return {"toolCallId": tool_call_id, "result": result}
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
            return {
                "toolCallId": tool_call_id,
                "result": json.dumps({"error": str(exc)}),
            }

    async def execute_schedule_dispatch(self, **kwargs: Any) -> str:
        parsed = ScheduleDispatchArgs.model_validate(kwargs)
        churn_ctx = (
            parsed.churn_risk_context.model_dump() if parsed.churn_risk_context else None
        )
        result = await self.dispatch_service.create_job(
            customer_id=parsed.customer_id,
            issue_type=parsed.issue_type,
            priority=parsed.priority,
            preferred_window=parsed.preferred_window,
            issue_description=parsed.issue_description,
            org_id=self.org_id,
            equipment_id=parsed.equipment_id,
            access_instructions=parsed.access_instructions,
            churn_context=churn_ctx,
        )
        if not result.get("success", True):
            return json.dumps(result)
        return json.dumps(result)

    async def execute_check_availability(self, **kwargs: Any) -> str:
        parsed = CheckAvailabilityArgs.model_validate(kwargs)
        tz_name = (
            self.org_settings.timezone
            if self.org_settings is not None
            else "America/Los_Angeles"
        )
        date_start, date_end = parse_date_range(
            parsed.preferred_date,
            parsed.num_days_to_check,
            tz_name,
        )
        preferred_tech = (
            uuid.UUID(parsed.preferred_technician_id)
            if parsed.preferred_technician_id
            else None
        )
        slots = await self.availability_service.get_available_slots(
            org_id=self.org_id,
            date_range_start=date_start,
            date_range_end=date_end,
            duration_minutes=parsed.duration_minutes,
            preferred_technician_id=preferred_tech,
        )
        if not slots:
            return json.dumps(
                {
                    "available_slots": [],
                    "message": (
                        "I couldn't find any open appointment slots in that time range. "
                        "Would you like me to check further out, or would you prefer "
                        "to call back later?"
                    ),
                }
            )

        formatted = [
            {
                "slot_label": slot.slot_label,
                "technician": slot.technician_name.split()[0],
                "technician_id": str(slot.technician_id),
                "date": slot.date.isoformat(),
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
            }
            for slot in slots
        ]
        earliest = formatted[0]
        count = len(formatted)
        return json.dumps(
            {
                "available_slots": formatted,
                "message": (
                    f"I found {count} available slot{'s' if count != 1 else ''}. "
                    f"The earliest is {earliest['slot_label']} with "
                    f"{earliest['technician']}. Which works best for you?"
                ),
            }
        )

    async def execute_query_churn_score(self, **kwargs: Any) -> str:
        customer_id = kwargs.get("customer_id", "")
        if _is_unresolved_template(customer_id):
            return json.dumps(
                {
                    "error": (
                        "customer_id is not available yet. Call get_customer_info first "
                        "to resolve the customer_id, then retry query_churn_score."
                    )
                }
            )

        parsed = QueryChurnScoreArgs.model_validate(kwargs)
        score = await self.churn_service.get_latest_score(
            parsed.customer_id, self.org_id
        )
        return json.dumps(score)

    async def execute_get_customer_info(self, **kwargs: Any) -> str:
        parsed = GetCustomerInfoArgs.model_validate(kwargs)
        profile = await self.customer_service.get_customer_info(
            parsed.lookup_method, parsed.lookup_value, self.org_id
        )
        return json.dumps(profile)

    async def execute_get_equipment_info(self, **kwargs: Any) -> str:
        parsed = GetEquipmentInfoArgs.model_validate(kwargs)
        cid = uuid.UUID(parsed.customer_id)

        # Ownership check: the customer must belong to this org.
        owner = await self.customer_service.get_by_id(cid, self.org_id)
        if owner is None:
            return json.dumps({"found": False, "equipment": []})

        if parsed.equipment_id:
            rows = await self.db.execute(
                text(
                    """
                    SELECT * FROM v_equipment_computed
                    WHERE customer_id = :customer_id AND equipment_id = :equipment_id
                    """
                ),
                {"customer_id": cid, "equipment_id": uuid.UUID(parsed.equipment_id)},
            )
            row = rows.mappings().first()
            if row is None:
                return json.dumps({"found": False, "equipment": []})
            return json.dumps({"found": True, "equipment": [_serialize_equipment_row(row)]})

        rows = await self.db.execute(
            text(
                """
                SELECT * FROM v_equipment_computed
                WHERE customer_id = :customer_id
                ORDER BY last_service_date DESC NULLS LAST
                """
            ),
            {"customer_id": cid},
        )
        equipment = [_serialize_equipment_row(r) for r in rows.mappings().all()]
        return json.dumps({"found": bool(equipment), "equipment": equipment})

    async def execute_rag_query(self, **kwargs: Any) -> str:
        parsed = RagKnowledgeQueryArgs.model_validate(kwargs)
        base_namespace = parsed.namespace_override or parsed.namespace
        if base_namespace is None and self.org_settings is not None:
            base_namespace = self.org_settings.pinecone_namespace
        if base_namespace is None:
            base_namespace = "faq_general"
        base_namespace = get_base_namespace(base_namespace)
        if self.org_slug:
            query_namespace = get_namespace(self.org_slug, base_namespace)
        else:
            query_namespace = base_namespace
        chunks = await self.rag_retriever.retrieve(
            query=parsed.query,
            namespace=query_namespace,
            top_k=parsed.top_k,
            filter_model=parsed.equipment_model,
        )
        return json.dumps({"retrieved_context": chunks})

    async def execute_lookup_service_info(self, **kwargs: Any) -> str:
        try:
            parsed = LookupServiceInfoArgs.model_validate(kwargs)
        except Exception as exc:
            return json.dumps(
                {
                    "error": (
                        "Provide at least one of query, category, or service_code. "
                        f"Details: {exc}"
                    )
                }
            )

        results = await self.service_catalog_service.lookup(
            org_id=self.org_id,
            query=parsed.query,
            category=parsed.category,
            service_code=parsed.service_code,
        )
        if not results:
            return json.dumps(
                {
                    "services_found": 0,
                    "results": [],
                    "message": (
                        "I couldn't find any services matching that request. "
                        "Try asking about a different service, or speak with a "
                        "technician for a custom quote."
                    ),
                }
            )

        formatted = [
            {
                "service_name": item.service_name,
                "price_range": format_price_range(item),
                "duration": format_duration(item),
                "description": item.description or "",
                "notes": item.price_notes or "",
            }
            for item in results
        ]
        count = len(formatted)
        return json.dumps(
            {
                "services_found": count,
                "results": formatted,
                "message": f"I found {count} service{'s' if count != 1 else ''} matching your question.",
            }
        )

    async def execute_create_ticket(self, **kwargs: Any) -> str:
        required_fields = (
            "customer_id",
            "ticket_type",
            "subject",
            "description",
            "priority",
        )
        missing_fields = [field for field in required_fields if not kwargs.get(field)]
        if missing_fields:
            return json.dumps(
                {
                    "error": (
                        "Missing required fields. Please collect customer_id, ticket_type, "
                        "subject, description, and priority before calling this tool."
                    )
                }
            )

        parsed = CreateSupportTicketArgs.model_validate(kwargs)
        # Ownership check: only create tickets for this org's customers.
        owner = await self.customer_service.get_by_id(
            uuid.UUID(parsed.customer_id), self.org_id
        )
        if owner is None:
            return json.dumps({"error": f"Customer {parsed.customer_id} not found"})
        ticket = await self.ticket_service.create_ticket(
            customer_id=uuid.UUID(parsed.customer_id),
            org_id=self.org_id,
            ticket_type=parsed.ticket_type,
            subject=parsed.subject,
            description=parsed.description,
            priority=parsed.priority,
            preferred_callback_time=parsed.preferred_callback_time,
        )
        return json.dumps({"success": True, "ticket": ticket})

    async def execute_create_customer(self, **kwargs: Any) -> str:
        parsed = CreateCustomerArgs.model_validate(kwargs)
        result = await self.customer_service.create_customer(parsed, self.org_id)
        if not result.get("success"):
            return json.dumps({"error": result.get("error", "Failed to create customer")})
        return json.dumps(
            {
                "status": "created",
                "customer_id": result["customer_id"],
                "message": result["message"],
            }
        )

    async def execute_update_customer(self, **kwargs: Any) -> str:
        try:
            parsed = UpdateCustomerArgs.model_validate(kwargs)
        except Exception as exc:
            return json.dumps(
                {
                    "error": (
                        "Invalid update request. Provide customer_id and at least one "
                        f"field to update. Details: {exc}"
                    )
                }
            )

        address_fields: dict[str, str] = {}
        updated_fields: list[str] = []
        for arg_name, patch_key in (
            ("service_address_line1", "line1"),
            ("service_address_line2", "line2"),
            ("service_address_city", "city"),
            ("service_address_state", "state"),
            ("service_address_zip", "zip"),
        ):
            value = getattr(parsed, arg_name)
            if value is not None:
                address_fields[patch_key] = value
                updated_fields.append(arg_name)

        payload_data: dict[str, Any] = {}
        for field in ("full_name", "phone_primary", "email", "notes"):
            value = getattr(parsed, field)
            if value is not None:
                payload_data[field] = value
                updated_fields.append(field)

        if address_fields:
            payload_data["address"] = CustomerAddressPatch(**address_fields)

        update_payload = CustomerUpdate(**payload_data)

        customer = await self.customer_service.update_customer(
            uuid.UUID(parsed.customer_id),
            update_payload,
            self.org_id,
        )
        if customer is None:
            return json.dumps({"error": f"Customer {parsed.customer_id} not found"})

        return json.dumps(
            {
                "status": "updated",
                "customer_id": parsed.customer_id,
                "updated_fields": sorted(set(updated_fields)),
                "message": "Account updated successfully.",
            }
        )

    async def execute_create_equipment(self, **kwargs: Any) -> str:
        parsed = CreateEquipmentArgs.model_validate(kwargs)
        equipment_service = EquipmentService(self.db)
        result = await equipment_service.create_equipment(parsed, self.org_id)
        if not result.get("success"):
            return json.dumps({"error": result.get("error", "Failed to create equipment")})
        return json.dumps(
            {
                "status": "created",
                "equipment_id": result["equipment_id"],
                "message": (
                    f"Equipment registered: {result['make']} {result['model']} "
                    f"({result['equipment_type']})."
                ),
            }
        )

    async def execute_update_dispatch(self, **kwargs: Any) -> str:
        parsed = UpdateDispatchArgs.model_validate(kwargs)
        result = await self.dispatch_service.update_job(parsed, self.org_id)
        if not result.get("success"):
            return json.dumps({"error": result.get("error", "Failed to update dispatch")})
        return json.dumps(
            {
                "status": "updated",
                "job_id": result["job_id"],
                "message": result["message"],
            }
        )


def _serialize_equipment_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, Decimal):
            data[key] = float(value)
        elif hasattr(value, "isoformat"):
            data[key] = value.isoformat()
        elif value is not None and key == "age_years_computed":
            data["age_years"] = float(value)
    if "age_years_computed" in data and "age_years" not in data:
        val = data.get("age_years_computed")
        data["age_years"] = float(val) if val is not None else None
    return data
