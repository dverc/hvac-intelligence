"""Vapi outbound call placement for retention campaigns."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.outbound_campaign import OutboundCallAttempt, OutboundCampaign
from app.services.compliance_service import (
    get_disclosure_text,
    get_org_display_name_from_db,
)
from app.services.sms_service import normalize_phone_to_e164

logger = logging.getLogger(__name__)

VAPI_CALL_URL = "https://api.vapi.ai/call"


def build_outbound_system_prompt(customer: Customer, campaign: OutboundCampaign) -> str:
    """System prompt for outbound retention agent with mandatory legal rules."""
    first_name = (customer.full_name or "there").split()[0]
    address_parts = [
        p
        for p in (customer.address_line1, customer.city, customer.state, customer.zip)
        if p
    ]
    address = ", ".join(address_parts) if address_parts else "on file"

    campaign_goals = {
        "REACTIVATION": "offer a complimentary maintenance check to re-engage the customer",
        "RETENTION": "offer a service discount to retain the customer",
        "REMINDER": "remind the customer about their upcoming appointment only",
    }
    goal = campaign_goals.get(campaign.campaign_type, campaign_goals["REACTIVATION"])

    recent_issue = ""
    metadata = customer.metadata_ or {}
    if metadata.get("last_issue_type"):
        recent_issue = f" Recent issue on file: {metadata['last_issue_type']}."

    return (
        f"You are calling {first_name} at {address}.{recent_issue}\n"
        f"Campaign goal: {goal}.\n"
        "Be concise, warm, and professional. Try to book a service appointment. "
        "If booking is not possible, offer a human callback.\n\n"
        "LEGAL REQUIREMENTS — THESE ARE MANDATORY AND CANNOT BE SKIPPED:\n"
        "1. You have already delivered the AI disclosure in your opening message. "
        "Do NOT claim to be human if asked directly.\n"
        "2. If the customer says STOP, OPT OUT, REMOVE ME, DON'T CALL, or similar: "
        "immediately say 'I've noted your request and you will not be contacted again. "
        "Have a good day.' Then end the call. Do NOT continue after an opt-out.\n"
        "3. If the customer asks to speak to a human, say 'I'll have a team member "
        "call you back shortly' and create a support ticket."
    )


class VapiOutboundService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def place_outbound_call(
        self,
        customer: Customer,
        org: Organization,
        campaign: OutboundCampaign,
        attempt_id: uuid.UUID,
    ) -> dict[str, Any]:
        settings = get_settings()
        phone = normalize_phone_to_e164(customer.phone_primary or "")
        if not phone:
            return {"success": False, "error": "invalid_phone"}

        display_name = await get_org_display_name_from_db(self.db, org)
        disclosure = get_disclosure_text(display_name, campaign.disclosure_style)
        first_message = (
            f"{disclosure} I'm calling about your HVAC service. Do you have a moment?"
        )

        org_phone_id = (org.vapi_phone_number_id or "").strip()
        org_assistant_id = (org.vapi_assistant_id or "").strip()
        phone_number_id = org_phone_id or settings.VAPI_PHONE_NUMBER_ID.strip()
        assistant_id = org_assistant_id or settings.VAPI_ASSISTANT_ID
        if not org_phone_id or not org_assistant_id:
            logger.warning(
                "Org %s has no Vapi config — falling back to platform defaults. "
                "Set vapi_assistant_id and vapi_phone_number_id in org settings.",
                org.org_id,
            )

        payload = {
            "assistantId": assistant_id,
            "phoneNumberId": phone_number_id,
            "customer": {"number": phone},
            "assistant": {
                "firstMessage": first_message,
                "model": {
                    "systemPrompt": build_outbound_system_prompt(customer, campaign),
                },
            },
        }

        attempt = await self.db.get(OutboundCallAttempt, attempt_id)
        if attempt is None:
            return {"success": False, "error": "attempt_not_found"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    VAPI_CALL_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
            if response.status_code >= 400:
                attempt.status = "FAILED"
                attempt.notes = response.text[:500]
                attempt.attempted_at = datetime.now(timezone.utc)
                await self.db.flush()
                logger.error(
                    "Vapi outbound call failed | status=%s | customer=%s",
                    response.status_code,
                    customer.customer_id,
                )
                return {"success": False, "error": response.text}

            body = response.json()
            vapi_call_id = str(body.get("id") or body.get("callId") or "")
            attempt.status = "CALLING"
            attempt.vapi_call_id = vapi_call_id or None
            attempt.attempted_at = datetime.now(timezone.utc)
            attempt.disclosure_delivered = True
            attempt.phone_number = phone
            await self.db.flush()
            return {"success": True, "vapi_call_id": vapi_call_id}
        except Exception as exc:
            logger.exception(
                "Vapi outbound call exception | customer=%s", customer.customer_id
            )
            attempt.status = "FAILED"
            attempt.notes = str(exc)[:500]
            attempt.attempted_at = datetime.now(timezone.utc)
            await self.db.flush()
            return {"success": False, "error": str(exc)}
