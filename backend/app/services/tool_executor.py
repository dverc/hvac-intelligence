from __future__ import annotations

import asyncio
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_call_id
from app.core.cache import (
    CUSTOMER_CACHE_TTL,
    cache_delete,
    cache_get,
    cache_set,
    customer_cache_key,
)
from app.core.metrics import observe_tool_execution
from app.models.organization import Organization
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
from app.services.audit_service import (
    ACTOR_VAPI,
    AUDIT_CREATE,
    AUDIT_UPDATE,
    log_action,
)
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService, normalize_phone
from app.services.dispatch_service import DispatchService
from app.services.equipment_service import EquipmentService
from app.services.service_area_service import is_address_serviceable
from app.services.skill_routing_service import get_required_skill
from app.services.service_catalog_service import (
    ServiceCatalogService,
    format_duration,
    format_price_range,
)
from app.services.ticket_service import TicketService
from app.services.window_parser import parse_date_range

logger = logging.getLogger(__name__)

async def _find_named_technician_from_window(
    db: AsyncSession,
    org_id: uuid.UUID,
    preferred_window: str,
) -> Any | None:
    """Match a word in preferred_window to an active technician's first name."""
    from sqlalchemy import select

    from app.models.technician import Technician

    stmt = select(Technician).where(
        Technician.org_id == org_id,
        Technician.employment_status == "ACTIVE",
    )
    techs = list((await db.execute(stmt)).scalars())
    for word in preferred_window.split():
        word_lower = word.lower()
        for tech in techs:
            first_name = tech.full_name.split()[0].lower()
            if word_lower == first_name:
                return tech
    return None


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
    "transfer_call": "execute_transfer_call",
    "check_service_area": "execute_check_service_area",
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
            "Executing Vapi tool call id=%s call_id=%s name=%s args=%s",
            tool_call_id,
            get_call_id(),
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
        from app.core.config import get_settings
        from app.core.redis_lock import LockNotAcquiredError, RedisLock, build_slot_lock_key
        from app.models.customer import Customer
        from app.services.window_parser import parse_preferred_window
        from redis.asyncio import Redis
        from sqlalchemy.orm import selectinload

        parsed = ScheduleDispatchArgs.model_validate(kwargs)
        churn_ctx = (
            parsed.churn_risk_context.model_dump() if parsed.churn_risk_context else None
        )
        create_kwargs = {
            "customer_id": parsed.customer_id,
            "issue_type": parsed.issue_type,
            "priority": parsed.priority,
            "preferred_window": parsed.preferred_window,
            "issue_description": parsed.issue_description,
            "org_id": self.org_id,
            "equipment_id": parsed.equipment_id,
            "access_instructions": parsed.access_instructions,
            "churn_context": churn_ctx,
        }

        redis_client = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
        try:
            customer = await self.dispatch_service.db.get(
                Customer,
                uuid.UUID(parsed.customer_id),
                options=[selectinload(Customer.preferred_tech)],
            )

            if customer is not None and customer.org_id == self.org_id:
                tz_name = await self.dispatch_service._get_org_timezone(self.org_id)
                named_tech = await _find_named_technician_from_window(
                    self.dispatch_service.db,
                    self.org_id,
                    parsed.preferred_window,
                )
                technician = None
                if named_tech is not None:
                    parsed_window = (
                        await self.dispatch_service._resolve_preferred_window(
                            parsed.preferred_window,
                            self.org_id,
                            named_tech.technician_id,
                            tz_name,
                        )
                    )
                    available, _ = (
                        await self.dispatch_service.availability.check_slot_available(
                            self.org_id,
                            named_tech.technician_id,
                            parsed_window.slot_date,
                            parsed_window.start_time,
                            parsed_window.end_time,
                        )
                    )
                    if available:
                        technician = named_tech
                if technician is None:
                    technician = await self.dispatch_service._select_technician(
                        customer, self.org_id
                    )
                    parsed_window = (
                        await self.dispatch_service._resolve_preferred_window(
                            parsed.preferred_window,
                            self.org_id,
                            technician.technician_id,
                            tz_name,
                        )
                    )
                create_kwargs["preferred_technician_id"] = technician.technician_id
                lock_key = build_slot_lock_key(
                    self.org_id,
                    technician.technician_id,
                    parsed_window.slot_date,
                    parsed.preferred_window,
                )
                try:
                    async with RedisLock(redis_client, lock_key):
                        result = await self.dispatch_service.create_job(**create_kwargs)
                except LockNotAcquiredError:
                    availability = json.loads(
                        await self.execute_check_availability(
                            preferred_date=parsed.preferred_window,
            issue_type=parsed.issue_type,
                        )
                    )
                    return json.dumps(
                        {
                            "success": False,
                            "error": "slot_taken",
                            "message": (
                                "That time slot was just taken by another booking. "
                                "Let me check what else is available."
                            ),
                            "available_slots": availability.get("available_slots", []),
                            "availability_message": availability.get("message"),
                        }
                    )
            else:
                result = await self.dispatch_service.create_job(**create_kwargs)

            if not result.get("success", True):
                return json.dumps(result)
            job_id = result.get("job_id")
            if job_id:
                try:
                    from app.models.dispatch_job import DispatchJob
                    from app.services.sms_service import SmsService

                    job = await self.db.get(
                        DispatchJob,
                        uuid.UUID(str(job_id)),
                        options=[
                            selectinload(DispatchJob.customer),
                            selectinload(DispatchJob.technician),
                        ],
                    )
                    if job is not None and job.customer is not None:
                        tz_name = (
                            await self.dispatch_service._get_org_timezone(self.org_id)
                            if self.org_id is not None
                            else "America/Los_Angeles"
                        )
                        tech_name = (
                            job.technician.full_name
                            if job.technician is not None
                            else "our technician"
                        )
                        await asyncio.to_thread(
                            SmsService().send_booking_confirmation,
                            job,
                            job.customer,
                            technician_name=tech_name,
                            timezone_name=tz_name,
                        )
                except Exception:
                    logger.exception(
                        "Failed to send booking confirmation SMS for job %s",
                        job_id,
                    )
                try:
                    from datetime import datetime, timedelta, timezone

                    from app.pipeline.tasks import (
                        send_appointment_reminder_1h,
                        send_appointment_reminder_24h,
                    )

                    scheduled_window_start = job.scheduled_window_start
                    if scheduled_window_start is None:
                        tz_name = (
                            await self.dispatch_service._get_org_timezone(self.org_id)
                            if self.org_id is not None
                            else "America/Los_Angeles"
                        )
                        parsed_window = parse_preferred_window(
                            parsed.preferred_window, tz_name
                        )
                        scheduled_window_start, _ = parsed_window.to_datetimes(
                            tz_name
                        )
                    now = datetime.now(timezone.utc)
                    if scheduled_window_start.tzinfo is None:
                        scheduled_window_start = scheduled_window_start.replace(
                            tzinfo=timezone.utc
                        )
                    else:
                        scheduled_window_start = scheduled_window_start.astimezone(
                            timezone.utc
                        )

                    eta_24h = scheduled_window_start - timedelta(hours=24)
                    if eta_24h > now:
                        send_appointment_reminder_24h.apply_async(
                            args=[str(job_id)], eta=eta_24h
                        )
                    else:
                        logger.info(
                            "Skipping 24h reminder for job %s — eta in the past",
                            job_id,
                        )

                    eta_1h = scheduled_window_start - timedelta(hours=1)
                    if eta_1h > now:
                        send_appointment_reminder_1h.apply_async(
                            args=[str(job_id)], eta=eta_1h
                        )
                    else:
                        logger.info(
                            "Skipping 1h reminder for job %s — eta in the past",
                            job_id,
                        )
                except Exception:
                    logger.exception(
                        "Failed to schedule appointment reminder SMS for job %s",
                        job_id,
                    )
            if self.org_id is not None and job_id:
                await log_action(
                    self.db,
                    str(self.org_id),
                    ACTOR_VAPI,
                    AUDIT_CREATE,
                    "dispatch_job",
                    str(job_id),
                    new_value={
                        "customer_id": parsed.customer_id,
                        "issue_type": parsed.issue_type,
                        "priority": parsed.priority,
                    },
                    call_id=get_call_id() or None,
                )
            return json.dumps(result)
        finally:
            await redis_client.aclose()

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
        preferred_tech = None
        if parsed.preferred_technician_id:
            try:
                preferred_tech = uuid.UUID(parsed.preferred_technician_id)
            except ValueError:
                logger.warning(
                    "Ignoring invalid preferred_technician_id %r — expected UUID",
                    parsed.preferred_technician_id,
                )
        issue_type = kwargs.get("issue_type")
        required_skill = (
            get_required_skill(str(issue_type)) if issue_type is not None else None
        )
        slots = await self.availability_service.get_available_slots(
            org_id=self.org_id,
            date_range_start=date_start,
            date_range_end=date_end,
            duration_minutes=parsed.duration_minutes,
            preferred_technician_id=preferred_tech,
            required_skill=required_skill,
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
        if parsed.lookup_method == "phone" and self.org_id is not None:
            cache_key = customer_cache_key(
                str(self.org_id), normalize_phone(parsed.lookup_value)
            )
            cached_profile = await cache_get(cache_key)
            if cached_profile is not None:
                return json.dumps(cached_profile)

        profile = await self.customer_service.get_customer_info(
            parsed.lookup_method, parsed.lookup_value, self.org_id
        )

        if parsed.lookup_method == "phone" and self.org_id is not None:
            cache_key = customer_cache_key(
                str(self.org_id), normalize_phone(parsed.lookup_value)
            )
            await cache_set(cache_key, profile, CUSTOMER_CACHE_TTL)

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
        if self.org_id is not None:
            await log_action(
                    self.db,
                    str(self.org_id),
                    ACTOR_VAPI,
                    AUDIT_CREATE,
                    "support_ticket",
                    ticket["ticket_id"],
                    new_value={
                        "customer_id": ticket["customer_id"],
                        "ticket_type": ticket["ticket_type"],
                        "subject": ticket["subject"],
                        "priority": ticket["priority"],
                    },
                    call_id=get_call_id() or None,
        )
        return json.dumps({"success": True, "ticket": ticket})

    async def execute_create_customer(self, **kwargs: Any) -> str:
        parsed = CreateCustomerArgs.model_validate(kwargs)
        result = await self.customer_service.create_customer(parsed, self.org_id)
        if not result.get("success"):
            return json.dumps({"error": result.get("error", "Failed to create customer")})
        if self.org_id is not None:
            await log_action(
                    self.db,
                    str(self.org_id),
                    ACTOR_VAPI,
                    AUDIT_CREATE,
                    "customer",
                    result["customer_id"],
                    new_value={
                        "name": parsed.full_name,
                        "phone": parsed.phone_primary,
                    },
                    call_id=get_call_id() or None,
                )
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

        existing_customer = await self.customer_service.get_by_id(
            uuid.UUID(parsed.customer_id), self.org_id
        )

        customer = await self.customer_service.update_customer(
            uuid.UUID(parsed.customer_id),
            update_payload,
            self.org_id,
        )
        if customer is None:
            return json.dumps({"error": f"Customer {parsed.customer_id} not found"})

        if self.org_id is not None:
            if existing_customer is not None:
                await cache_delete(
                    customer_cache_key(
                        str(self.org_id),
                        normalize_phone(existing_customer.phone_primary),
                    )
                )
            await cache_delete(
                customer_cache_key(
                    str(self.org_id), normalize_phone(customer.phone_primary)
                )
            )

        audit_new_value: dict[str, Any] = {}
        for key, value in payload_data.items():
            if hasattr(value, "model_dump"):
                audit_new_value[key] = value.model_dump()
            else:
                audit_new_value[key] = value
        if self.org_id is not None:
            await log_action(
                    self.db,
                    str(self.org_id),
                    ACTOR_VAPI,
                    AUDIT_UPDATE,
                    "customer",
                    parsed.customer_id,
                    new_value=audit_new_value,
                    call_id=get_call_id() or None,
                )

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
        if self.org_id is not None:
            await log_action(
                    self.db,
                    str(self.org_id),
                    ACTOR_VAPI,
                    AUDIT_CREATE,
                    "equipment",
                    result["equipment_id"],
                    new_value={
                        "make": result.get("make"),
                        "model": result.get("model"),
                    },
                    call_id=get_call_id() or None,
                )
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
        if self.org_id is not None:
            await log_action(
                    self.db,
                    str(self.org_id),
                    ACTOR_VAPI,
                    AUDIT_UPDATE,
                    "dispatch_job",
                    str(result["job_id"]),
                    new_value=parsed.model_dump(exclude_none=True),
                    call_id=get_call_id() or None,
                )
        return json.dumps(
            {
                "status": "updated",
                "job_id": result["job_id"],
                "message": result["message"],
            }
        )

    async def execute_check_service_area(self, **kwargs: Any) -> str:
        try:
            address = str(kwargs.get("address") or "").strip()
            if not address:
                return "Please provide the service address so I can check coverage."

            org = await self.db.get(Organization, self.org_id)
            settings = org.settings or {} if org is not None else {}
            _serviceable, message = is_address_serviceable(address, settings)
            return message
        except Exception:
            logger.exception("check_service_area failed | org_id=%s", self.org_id)
            return (
                "I couldn't verify the service area right now — we can continue with booking."
            )

    async def execute_transfer_call(self, **kwargs: Any) -> str | dict[str, Any]:
        try:
            reason = kwargs.get("reason", "Customer requested human agent")
            org = await self.db.get(Organization, self.org_id)
            transfer_phone_number = org.transfer_phone_number if org is not None else None
            if not transfer_phone_number or not str(transfer_phone_number).strip():
                logger.info(
                    "transfer_call unavailable | org_id=%s reason=%s",
                    self.org_id,
                    reason,
                )
                return (
                    "Transfer is not available for this account. "
                    "I'll create a callback request for you instead."
                )

            logger.info(
                "transfer_call initiated | org_id=%s reason=%s",
                self.org_id,
                reason,
            )
            return {
                "destination": {
                    "type": "number",
                    "number": transfer_phone_number,
                },
                "message": "Please hold while I transfer you to our team.",
            }
        except Exception:
            logger.exception("transfer_call failed | org_id=%s", self.org_id)
            return (
                "I'm unable to transfer the call right now. "
                "I'll create a callback request for you instead."
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
