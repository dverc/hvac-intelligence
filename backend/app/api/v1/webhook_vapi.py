from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api import deps
from app.core.cache import ORG_CACHE_TTL, cache_get, cache_set, org_cache_key
from app.core.logging_config import set_call_id
from app.core.config import get_settings
from app.core.constants import SEED_ORG_ID
from app.core.metrics import vapi_webhook_total
from app.core.rate_limit import limiter
from app.core.database import get_session_factory
from app.pipeline.event_bus import publish_call_active_event
from app.schemas.organization import OrganizationSettings
from app.services.hours_service import get_hours_context, is_within_business_hours
from app.services.tenant_service import TenantService, normalize_phone
from app.services.transcript_service import TranscriptService
from app.services.vapi_payload import extract_phone_from_vapi_payload
from sqlalchemy.ext.asyncio import AsyncSession
router = APIRouter(prefix="/webhook/vapi", tags=["vapi"])
logger = logging.getLogger(__name__)


def _customer_tier_system_prompt_prefix(customer_tier: str) -> str:
    """VIP/preferred tier instructions prepended to call-start system prompt."""
    tier = (customer_tier or "standard").lower()
    if tier == "vip":
        return (
            "VIP CUSTOMER: This is a VIP customer. Greet them warmly and personally. "
            "Mention that we truly value their loyalty. Offer priority scheduling — "
            "give them the earliest available slot first. Waive the diagnostic fee if mentioned."
        )
    if tier == "preferred":
        return (
            "PREFERRED CUSTOMER: This is a preferred customer. Treat them with extra warmth. "
            "Mention our annual maintenance plan if relevant."
        )
    return ""


def _normalize_signature(signature_header: str) -> bytes | None:
    """Parse hex digest from Vapi signature header variants."""
    if not signature_header:
        return None
    value = signature_header.strip()
    if value.lower().startswith("sha256="):
        value = value.split("=", 1)[1].strip()
    if value.lower().startswith("v1="):
        value = value.split("=", 1)[1].strip()
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def verify_vapi_signature(request_body: bytes, signature_header: str | None, secret: str) -> bool:
    """
    Timing-safe HMAC-SHA256 verification of Vapi webhook payloads.
    Compares raw digest bytes to prevent timing leaks from string comparison.
    """
    settings = get_settings()
    if settings.VAPI_WEBHOOK_HMAC_BYPASS and settings.ENVIRONMENT != "production":
        return True

    if not secret or not signature_header:
        return False

    provided = _normalize_signature(signature_header)
    if provided is None:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        request_body,
        hashlib.sha256,
    ).digest()

    return hmac.compare_digest(expected, provided)


def _extract_call_id_from_body(body_bytes: bytes) -> str:
    try:
        payload = json.loads(body_bytes)
        message = payload.get("message", payload)
        if isinstance(message, dict):
            call = message.get("call", {})
            if isinstance(call, dict) and call.get("id"):
                return str(call["id"])
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return "unknown"


def _event_type(message: dict[str, Any]) -> str:
    raw = message.get("type") or message.get("event") or ""
    return str(raw).lower().replace(".", "-").replace("_", "-")


def _extract_phone_from_call(message: dict[str, Any]) -> Optional[str]:
    return extract_phone_from_vapi_payload(message)


def _normalize_phones_in_call_message(message: dict[str, Any]) -> None:
    """Normalise caller and called business numbers in-place for tenant resolution."""
    call = message.get("call")
    if not isinstance(call, dict):
        call = {}
        message["call"] = call

    for container in (call, message):
        customer = container.get("customer")
        if isinstance(customer, dict) and customer.get("number"):
            customer["number"] = normalize_phone(str(customer["number"]))

    for container in (call, message):
        phone_number = container.get("phoneNumber") or container.get("phone_number")
        if isinstance(phone_number, dict) and phone_number.get("number"):
            phone_number["number"] = normalize_phone(str(phone_number["number"]))
        elif isinstance(phone_number, str) and phone_number:
            container["phoneNumber"] = {"number": normalize_phone(phone_number)}

    for container in (call, message):
        to = container.get("to")
        if isinstance(to, str) and to:
            container["to"] = normalize_phone(to)


async def _process_call_end_background(call_data: dict[str, Any], org_id: str) -> None:
    async with get_session_factory()() as session:
        try:
            call = call_data.get("call", call_data)
            call_id = str(call.get("id") or call_data.get("call_id") or "")

            rag_chunks_used: list[dict[str, Any]] = []
            tool_executor = None
            if call_id:
                try:
                    tool_executor = await deps.build_tool_executor(session)
                    rag_chunks_used = await tool_executor.get_rag_chunks_summary(call_id)
                except Exception:
                    logger.exception(
                        "Failed to load RAG chunk summary | call_id=%s",
                        call_id,
                    )

            service = TranscriptService(session)
            result = await service.process_completed_call(
                call_data,
                uuid.UUID(org_id),
                rag_chunks_used=rag_chunks_used or None,
            )

            if call_id and rag_chunks_used and tool_executor is not None:
                try:
                    await tool_executor.clear_rag_chunks_cache(call_id)
                except Exception:
                    logger.debug(
                        "Failed to clear RAG chunks cache | call_id=%s",
                        call_id,
                        exc_info=True,
                    )
            if result and result.get("customer_id"):
                duration = int(result.get("duration_seconds") or 0)
                outcome = str(result.get("call_outcome") or "").upper()
                if duration >= 30 and outcome not in {"ABANDONED", "OPT_OUT"}:
                    from app.services.outbound_service import OutboundService

                    outbound = OutboundService(session)
                    call_id = str(result.get("call_id") or "")
                    await outbound.record_inbound_engagement_consent(
                        uuid.UUID(str(result["customer_id"])),
                        uuid.UUID(org_id),
                        call_id,
                    )
            await session.commit()
            if result:
                cost_display = result["call_cost_usd"]
                if cost_display is None:
                    cost_str = "N/A"
                else:
                    cost_str = f"{cost_display:.4f}"
                logger.info(
                    "Transcript persisted | call_id=%s | customer_id=%s | duration=%ss | cost=$%s",
                    result["call_id"],
                    result.get("customer_id"),
                    result.get("duration_seconds"),
                    cost_str,
                )
        except Exception:
            await session.rollback()
            logger.exception("Failed to process completed call in background")


@router.post("")
@limiter.limit("120/minute", override_defaults=True)
async def handle_vapi_webhook(
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
) -> JSONResponse:
    body_bytes = await request.body()
    set_call_id(_extract_call_id_from_body(body_bytes))
    try:
        settings = get_settings()

        signature_header = (
            request.headers.get("x-vapi-signature")
            or request.headers.get("X-Vapi-Signature")
            or request.headers.get("x-vapi-secret")
            or request.headers.get("X-Vapi-Secret")
        )
        if not verify_vapi_signature(
            body_bytes, signature_header, settings.VAPI_WEBHOOK_SECRET
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        message = payload.get("message", payload)
        event_type = _event_type(message)
        call = message.get("call", {})
        call_id = call.get("id", "unknown")

        logger.info("Vapi event: %s | call_id: %s", event_type, call_id)
        vapi_webhook_total.labels(event_type=event_type).inc()

        # Resolve the tenant for THIS call (per-call, never assumed process-wide).
        tenant_service = TenantService(db)
        org_id = await tenant_service.resolve_org_for_call(str(call_id), message)
        org = await tenant_service.get_tenant_by_id(org_id)
        org_settings = OrganizationSettings.model_validate(org.settings or {}) if org else None
        if org is not None:
            logger.info(
                "Tenant resolved: %s (org_id=%s) | call_id=%s",
                org.org_name,
                org_id,
                call_id,
            )

        if event_type == "tool-calls":
            tool_executor = await deps.build_tool_executor(db)
            tool_executor.set_tenant(
                org_id,
                org_settings,
                org_slug=org.slug if org is not None else None,
            )
            tool_call_list = message.get("toolCallList", [])
            logger.info(
                "Vapi tool-calls raw payload (call_id=%s): %s",
                call_id,
                json.dumps(tool_call_list, default=str),
            )
            results = await tool_executor.execute_batch(tool_call_list)
            return JSONResponse({"results": results})

        if event_type in {"call-start", "call-started", "assistant-started"}:
            try:
                _normalize_phones_in_call_message(message)

                try:
                    call_start_org_id = await tenant_service.resolve_org_for_call(
                        str(call_id), message
                    )
                except Exception:
                    logger.warning(
                        "Tenant resolution raised for call-start | call_id=%s",
                        call_id,
                        exc_info=True,
                    )
                    call_start_org_id = None

                if call_start_org_id is None:
                    logger.warning(
                        "Tenant resolution returned None for call-start | call_id=%s; "
                        "using fallback org",
                        call_id,
                    )
                    call_start_org_id = SEED_ORG_ID

                cached_org_settings = await cache_get(org_cache_key(str(call_start_org_id)))
                call_start_org = await tenant_service.get_tenant_by_id(call_start_org_id)
                if cached_org_settings is not None:
                    call_start_org_settings = OrganizationSettings.model_validate(
                        cached_org_settings
                    )
                elif call_start_org is not None:
                    settings_dict = dict(call_start_org.settings or {})
                    call_start_org_settings = OrganizationSettings.model_validate(
                        settings_dict
                    )
                    await cache_set(
                        org_cache_key(str(call_start_org_id)),
                        settings_dict,
                        ORG_CACHE_TTL,
                    )
                else:
                    call_start_org_settings = None

                tool_executor = await deps.build_tool_executor(db)
                tool_executor.set_tenant(
                    call_start_org_id,
                    call_start_org_settings,
                    org_slug=call_start_org.slug if call_start_org is not None else None,
                )
                phone = _extract_phone_from_call(message)
                if not phone:
                    logger.warning(
                        "Missing caller phone number for call-start | call_id=%s",
                        call_id,
                    )

                enrichment = await tool_executor.customer_service.get_call_context(
                    phone or "", call_id, call_start_org
                )
                variable_values = enrichment["variable_values"]
                logger.info(
                    "Call context for %s (call_id=%s): customer=%s, churn=%s",
                    phone,
                    call_id,
                    variable_values.get("customer_name"),
                    variable_values.get("churn_risk"),
                )

                customer = None
                if phone and call_start_org is not None:
                    customer = await tool_executor.customer_service.lookup_by_phone(
                        phone, call_start_org_id
                    )
                    if customer is not None:
                        score = await tool_executor.churn_service.get_latest_score(
                            str(customer.customer_id), call_start_org_id
                        )
                        if score.get("risk_tier") in ("HIGH", "CRITICAL"):
                            await publish_call_active_event(
                                org_id=str(call_start_org_id),
                                call_id=str(call_id),
                                customer_id=str(customer.customer_id),
                                customer_name=customer.full_name,
                                churn_risk_tier=score["risk_tier"],
                                churn_probability=float(score["churn_probability"]),
                                intervention_triggered=True,
                            )

                system_prompt = enrichment["system_prompt_injection"]
                if phone:
                    system_prompt = system_prompt.replace("{{caller_phone}}", phone)
                    system_prompt = (
                        f"FIRST ACTION: The caller's phone number is {phone}. "
                        "Start by calling get_customer_info with lookup_method='phone' "
                        f"and lookup_value='{phone}' immediately.\n\n"
                        f"{system_prompt}"
                    )
                if customer is not None:
                    tier_prefix = _customer_tier_system_prompt_prefix(customer.customer_tier)
                    if tier_prefix:
                        system_prompt = f"{tier_prefix}\n\n{system_prompt}"
                if call_start_org is not None and call_start_org.agent_name:
                    system_prompt = (
                        f"Your name is {call_start_org.agent_name}. {system_prompt}"
                    )
                if call_start_org is not None:
                    org_settings_dict = (
                        cached_org_settings
                        if cached_org_settings is not None
                        else dict(call_start_org.settings or {})
                    )
                    if not is_within_business_hours(org_settings_dict):
                        hours_context = get_hours_context(org_settings_dict)
                        system_prompt = (
                            "AFTER-HOURS NOTICE: This call is being received outside normal "
                            f"business hours. {hours_context} Acknowledge the time warmly. "
                            "Offer the caller two options: (1) emergency dispatch — explain "
                            "there is a premium after-hours rate and ask if they want to "
                            "proceed, or (2) schedule for the next available business day "
                            "slot. Do not promise standard pricing for after-hours calls.\n\n"
                            f"{system_prompt}"
                        )

                from app.services.compliance_service import (
                    get_inbound_disclosure_text,
                    get_org_display_name,
                )

                if call_start_org is not None:
                    company_name = get_org_display_name(call_start_org)
                    consent_capture = (
                        "CONSENT CAPTURE — LEGAL REQUIREMENT:\n"
                        f"- At the start of EVERY call, before anything else, say: "
                        f"'{get_inbound_disclosure_text(company_name)}'\n"
                        "- If the customer agrees to proceed: this constitutes verbal "
                        "consent to the call.\n"
                        "- If the customer asks to opt out or says they don't want calls: "
                        "say 'I've noted that. You won't be contacted again. Goodbye.' "
                        "and end the call immediately.\n"
                        "- Do NOT skip this disclosure under any circumstances.\n\n"
                    )
                else:
                    consent_capture = ""

                system_prompt = (
                    f"{consent_capture}"
                    "TOOL RULES - CRITICAL:\n"
                    "- create_support_ticket: You MUST collect customer_id, ticket_type, "
                    "subject, description, and priority BEFORE calling this tool. Never call "
                    "create_support_ticket with empty arguments. If you do not have all "
                    "fields, ask the customer for the missing information first.\n"
                    "- schedule_dispatch: After calling check_availability, use the "
                    "technician name from the availability results. Do not include "
                    "technician names in preferred_window — pass only the date and time "
                    "window.\n"
                    "- schedule_dispatch: After schedule_dispatch completes successfully, "
                    "the tool response will include the assigned technician's name in the "
                    "result. ALWAYS read the technician name from the dispatch result and "
                    "confirm it to the customer. Never assume the technician name from "
                    "your own memory or the preferred_window string.\n"
                    "- schedule_dispatch: If a customer says the wrong technician was "
                    "assigned after a booking, do NOT try to re-book. Instead say: "
                    "\"I apologize for the mix-up. I've noted your preference for "
                    "[technician name] and our team will ensure [technician name] is "
                    "assigned when they call to confirm your appointment.\" Then end the "
                    "call gracefully.\n"
                    "- schedule_dispatch: If schedule_dispatch returns an error 3 or more "
                    "times in a row for the same time slot, STOP trying that slot. Tell "
                    "the customer: 'I'm having trouble booking that slot right now. Let me "
                    "create a callback request so our team can confirm your appointment.' "
                    "Then call create_support_ticket with ticket_type='MANAGER_CALLBACK' "
                    "and a clear description of the desired booking details. Do NOT confirm "
                    "a booking that was not successfully created.\n"
                    "- When a customer asks whether they will receive an SMS or text "
                    "confirmation: say 'Yes, you will receive a text confirmation shortly "
                    "after this call ends.' Do not create a support ticket for this "
                    "question.\n\n"
                    f"{system_prompt}"
                )

                assistant_overrides: dict[str, Any] = {
                    "variableValues": variable_values,
                    "model": {
                        "systemPrompt": system_prompt,
                    },
                }
                assistant_id = None
                if call_start_org is not None and call_start_org.vapi_assistant_id:
                    assistant_id = call_start_org.vapi_assistant_id.strip()
                if not assistant_id:
                    assistant_id = get_settings().VAPI_ASSISTANT_ID
                if assistant_id:
                    assistant_overrides["assistantId"] = assistant_id
                if call_start_org is not None:
                    assistant_overrides["firstMessage"] = get_inbound_disclosure_text(
                        get_org_display_name(call_start_org)
                    )
                elif enrichment.get("first_message"):
                    assistant_overrides["firstMessage"] = enrichment["first_message"]

                return JSONResponse({"assistantOverrides": assistant_overrides})
            except Exception:
                logger.exception(
                    "call-start processing failed | call_id=%s", call_id
                )
                return JSONResponse(
                    {
                        "status": "ok",
                        "warning": "call-start processing failed, continuing",
                    }
                )

        if event_type in {"call-end", "call-ended", "end-of-call-report"}:
            background = BackgroundTasks()
            background.add_task(_process_call_end_background, message, str(org_id))
            return JSONResponse({"status": "accepted"}, background=background)

        return JSONResponse({"status": "ok"})
    finally:
        set_call_id("")
