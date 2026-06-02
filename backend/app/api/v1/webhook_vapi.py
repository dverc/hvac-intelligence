from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_tool_executor
from app.core.config import get_settings
from app.core.metrics import vapi_webhook_total
from app.core.rate_limit import limiter
from app.core.database import get_session_factory
from app.pipeline.event_bus import publish_call_active_event
from app.schemas.organization import OrganizationSettings
from app.services.tenant_service import TenantService
from app.services.tool_executor import ToolExecutor
from app.services.transcript_service import TranscriptService
router = APIRouter(prefix="/webhook/vapi", tags=["vapi"])
logger = logging.getLogger(__name__)


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


def _event_type(message: dict[str, Any]) -> str:
    raw = message.get("type") or message.get("event") or ""
    return str(raw).lower().replace(".", "-").replace("_", "-")


def _extract_phone_from_call(message: dict[str, Any]) -> Optional[str]:
    if number := (message.get("customer") or {}).get("number"):
        return str(number)
    call = message.get("call", {})
    if number := (call.get("customer") or {}).get("number"):
        return str(number)
    phone_number = (
        call.get("phoneNumber")
        or call.get("phone_number")
        or message.get("phoneNumber")
        or message.get("phone_number")
    )
    if isinstance(phone_number, dict):
        return phone_number.get("number")
    if isinstance(phone_number, str):
        return phone_number
    return None


async def _process_call_end_background(call_data: dict[str, Any], org_id: str) -> None:
    async with get_session_factory()() as session:
        try:
            service = TranscriptService(session)
            result = await service.process_completed_call(
                call_data, uuid.UUID(org_id)
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
    tool_executor: ToolExecutor = Depends(get_tool_executor),
) -> JSONResponse:
    settings = get_settings()
    body_bytes = await request.body()

    signature_header = (
        request.headers.get("x-vapi-signature")
        or request.headers.get("X-Vapi-Signature")
        or request.headers.get("x-vapi-secret")
        or request.headers.get("X-Vapi-Secret")
    )
    if not verify_vapi_signature(body_bytes, signature_header, settings.VAPI_WEBHOOK_SECRET):
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
    tenant_service = TenantService(tool_executor.db)
    org_id = await tenant_service.resolve_org_for_call(str(call_id), message)
    org = await tenant_service.get_tenant_by_id(org_id)
    org_settings = OrganizationSettings.model_validate(org.settings or {}) if org else None
    tool_executor.set_tenant(org_id, org_settings)
    if org is not None:
        logger.info(
            "Tenant resolved: %s (org_id=%s) | call_id=%s",
            org.org_name,
            org_id,
            call_id,
        )

    if event_type == "tool-calls":
        tool_call_list = message.get("toolCallList", [])
        logger.info(
            "Vapi tool-calls raw payload (call_id=%s): %s",
            call_id,
            json.dumps(tool_call_list, default=str),
        )
        results = await tool_executor.execute_batch(tool_call_list)
        return JSONResponse({"results": results})

    if event_type in {"call-start", "call-started"}:
        phone = _extract_phone_from_call(message)
        if not phone:
            raise HTTPException(status_code=422, detail="Missing caller phone number")
        if org is None:
            raise HTTPException(status_code=500, detail="Tenant resolution failed")

        enrichment = await tool_executor.customer_service.get_call_context(
            phone, call_id, org
        )
        variable_values = enrichment["variable_values"]
        logger.info(
            "Call context for %s (call_id=%s): customer=%s, churn=%s",
            phone,
            call_id,
            variable_values.get("customer_name"),
            variable_values.get("churn_risk"),
        )

        customer = await tool_executor.customer_service.lookup_by_phone(phone, org_id)
        if customer is not None:
            score = await tool_executor.churn_service.get_latest_score(
                str(customer.customer_id), org_id
            )
            if score.get("risk_tier") in ("HIGH", "CRITICAL"):
                await publish_call_active_event(
                    call_id=str(call_id),
                    customer_id=str(customer.customer_id),
                    customer_name=customer.full_name,
                    churn_risk_tier=score["risk_tier"],
                    churn_probability=float(score["churn_probability"]),
                    intervention_triggered=True,
                )

        assistant_overrides: dict[str, Any] = {
            "variableValues": variable_values,
            "model": {
                "systemPrompt": enrichment["system_prompt_injection"],
            },
        }
        if enrichment.get("first_message"):
            assistant_overrides["firstMessage"] = enrichment["first_message"]

        return JSONResponse({"assistantOverrides": assistant_overrides})

    if event_type in {"call-end", "call-ended", "end-of-call-report"}:
        background = BackgroundTasks()
        background.add_task(_process_call_end_background, message, str(org_id))
        return JSONResponse({"status": "accepted"}, background=background)

    return JSONResponse({"status": "ok"})
