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
from app.rag.retriever import RAGRetriever
from app.schemas.customer import CustomerAddressPatch, CustomerUpdate
from app.schemas.tools import (
    CreateCustomerArgs,
    CreateEquipmentArgs,
    CreateSupportTicketArgs,
    GetCustomerInfoArgs,
    GetEquipmentInfoArgs,
    QueryChurnScoreArgs,
    RagKnowledgeQueryArgs,
    ScheduleDispatchArgs,
    UpdateCustomerArgs,
    UpdateDispatchArgs,
)
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.equipment_service import EquipmentService
from app.services.ticket_service import TicketService

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


class ToolExecutor:
    def __init__(
        self,
        customer_service: CustomerService,
        dispatch_service: DispatchService,
        churn_service: ChurnService,
        ticket_service: TicketService,
        rag_retriever: RAGRetriever,
    ) -> None:
        self.customer_service = customer_service
        self.dispatch_service = dispatch_service
        self.churn_service = churn_service
        self.ticket_service = ticket_service
        self.rag_retriever = rag_retriever

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
            args,
        )

        handler_name = TOOL_REGISTRY.get(tool_name)
        if not handler_name:
            return {
                "toolCallId": tool_call_id,
                "result": json.dumps({"error": f"Unknown tool: {tool_name}"}),
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
            equipment_id=parsed.equipment_id,
            access_instructions=parsed.access_instructions,
            churn_context=churn_ctx,
        )
        return json.dumps(result)

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
        score = await self.churn_service.get_latest_score(parsed.customer_id)
        return json.dumps(score)

    async def execute_get_customer_info(self, **kwargs: Any) -> str:
        parsed = GetCustomerInfoArgs.model_validate(kwargs)
        profile = await self.customer_service.get_customer_info(
            parsed.lookup_method, parsed.lookup_value
        )
        return json.dumps(profile)

    async def execute_get_equipment_info(self, **kwargs: Any) -> str:
        parsed = GetEquipmentInfoArgs.model_validate(kwargs)
        cid = uuid.UUID(parsed.customer_id)

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
        chunks = await self.rag_retriever.retrieve(
            query=parsed.query,
            namespace=parsed.namespace,
            top_k=parsed.top_k,
            filter_model=parsed.equipment_model,
        )
        return json.dumps({"retrieved_context": chunks})

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
        ticket = await self.ticket_service.create_ticket(
            customer_id=uuid.UUID(parsed.customer_id),
            ticket_type=parsed.ticket_type,
            subject=parsed.subject,
            description=parsed.description,
            priority=parsed.priority,
            preferred_callback_time=parsed.preferred_callback_time,
        )
        return json.dumps({"success": True, "ticket": ticket})

    async def execute_create_customer(self, **kwargs: Any) -> str:
        parsed = CreateCustomerArgs.model_validate(kwargs)
        result = await self.customer_service.create_customer(parsed)
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
        result = await equipment_service.create_equipment(parsed)
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
        result = await self.dispatch_service.update_job(parsed)
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
