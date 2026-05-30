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
from app.schemas.tools import (
    CreateSupportTicketArgs,
    GetCustomerInfoArgs,
    GetEquipmentInfoArgs,
    QueryChurnScoreArgs,
    RagKnowledgeQueryArgs,
    ScheduleDispatchArgs,
)
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.ticket_service import TicketService

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, str] = {
    "schedule_dispatch": "execute_schedule_dispatch",
    "query_churn_score": "execute_query_churn_score",
    "get_customer_info": "execute_get_customer_info",
    "get_equipment_info": "execute_get_equipment_info",
    "rag_knowledge_query": "execute_rag_query",
    "create_support_ticket": "execute_create_ticket",
}


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
        tool_name = tool_call.get("name", "")
        tool_call_id = tool_call.get("id", "")
        raw_args = tool_call.get("arguments", {})
        args: dict[str, Any]
        if isinstance(raw_args, str):
            args = json.loads(raw_args) if raw_args else {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}

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
