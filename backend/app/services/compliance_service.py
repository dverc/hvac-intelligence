"""TCPA/FCC/California compliance gatekeeper for outbound calling."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONSENT_TYPE_OUTBOUND_CALL,
    DEFAULT_ORG_TIMEZONE,
    DISCLOSURE_STYLE_FORMAL,
    DISCLOSURE_STYLE_FRIENDLY,
    OUTBOUND_ATTEMPT_LOOKBACK_DAYS,
    TCPA_CALLING_HOURS_END,
    TCPA_CALLING_HOURS_START,
)
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.outbound_campaign import ConsentRecord, OutboundCallAttempt
from app.schemas.organization import OrganizationSettings
from app.services.sms_service import normalize_phone_to_e164

# Major US area codes → IANA timezone (defaults to Pacific when unknown)
_AREA_CODE_TIMEZONE: dict[str, str] = {
    "201": "America/New_York",
    "202": "America/New_York",
    "203": "America/New_York",
    "205": "America/Chicago",
    "206": "America/Los_Angeles",
    "212": "America/New_York",
    "213": "America/Los_Angeles",
    "214": "America/Chicago",
    "215": "America/New_York",
    "216": "America/New_York",
    "301": "America/New_York",
    "303": "America/Denver",
    "305": "America/New_York",
    "310": "America/Los_Angeles",
    "312": "America/Chicago",
    "313": "America/New_York",
    "314": "America/Chicago",
    "323": "America/Los_Angeles",
    "347": "America/New_York",
    "404": "America/New_York",
    "405": "America/Chicago",
    "408": "America/Los_Angeles",
    "415": "America/Los_Angeles",
    "424": "America/Los_Angeles",
    "469": "America/Chicago",
    "480": "America/Phoenix",
    "503": "America/Los_Angeles",
    "510": "America/Los_Angeles",
    "512": "America/Chicago",
    "516": "America/New_York",
    "602": "America/Phoenix",
    "617": "America/New_York",
    "619": "America/Los_Angeles",
    "626": "America/Los_Angeles",
    "646": "America/New_York",
    "650": "America/Los_Angeles",
    "702": "America/Los_Angeles",
    "703": "America/New_York",
    "704": "America/New_York",
    "713": "America/Chicago",
    "714": "America/Los_Angeles",
    "718": "America/New_York",
    "720": "America/Denver",
    "732": "America/New_York",
    "747": "America/Los_Angeles",
    "760": "America/Los_Angeles",
    "773": "America/Chicago",
    "786": "America/New_York",
    "801": "America/Denver",
    "805": "America/Los_Angeles",
    "818": "America/Los_Angeles",
    "832": "America/Chicago",
    "847": "America/Chicago",
    "858": "America/Los_Angeles",
    "901": "America/Chicago",
    "909": "America/Los_Angeles",
    "916": "America/Los_Angeles",
    "917": "America/New_York",
    "925": "America/Los_Angeles",
    "949": "America/Los_Angeles",
    "972": "America/Chicago",
    "973": "America/New_York",
}


def get_org_display_name(org: Organization) -> str:
    """Client company name for disclosures — never 'HVAC Intelligence'."""
    settings = OrganizationSettings.model_validate(org.settings or {})
    display = (settings.outbound_display_name or "").strip()
    if display:
        return display
    return org.org_name


def get_disclosure_text(org_display_name: str, disclosure_style: str) -> str:
    """AI + recording disclosure (mandatory, non-removable)."""
    name = org_display_name.strip() or "your HVAC service provider"
    style = disclosure_style.upper()
    if style == DISCLOSURE_STYLE_FORMAL:
        return (
            f"This call is being handled by an artificial intelligence system on behalf of "
            f"{name}. This call is recorded. You have the right to speak with a human "
            f"representative at any time."
        )
    return (
        f"Hi, this is an AI virtual assistant calling on behalf of {name}. "
        f"This call may be recorded for quality assurance."
    )


def get_inbound_disclosure_text(org_display_name: str) -> str:
    """Opening disclosure for inbound calls."""
    name = org_display_name.strip() or "your HVAC service provider"
    return (
        f"Hi, this is an AI virtual assistant from {name}. "
        f"This call may be recorded. May I have a moment of your time?"
    )


def _extract_area_code(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) >= 10:
        return digits[:3]
    return None


def timezone_for_phone(phone: str) -> str:
    area = _extract_area_code(phone)
    if area and area in _AREA_CODE_TIMEZONE:
        return _AREA_CODE_TIMEZONE[area]
    return DEFAULT_ORG_TIMEZONE


def check_calling_hours(
    customer_phone: str,
    calling_hours_start: int,
    calling_hours_end: int,
    *,
    now: datetime | None = None,
) -> bool:
    """True when current local time is within the legal TCPA window and org window."""
    start_hour = max(calling_hours_start, TCPA_CALLING_HOURS_START)
    end_hour = min(calling_hours_end, TCPA_CALLING_HOURS_END)
    if start_hour >= end_hour:
        return False

    tz_name = timezone_for_phone(customer_phone)
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz_name))
    return start_hour <= local_now.hour < end_hour


class ComplianceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _count_recent_attempts(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
        max_attempts: int,
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=OUTBOUND_ATTEMPT_LOOKBACK_DAYS)
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(OutboundCallAttempt)
                .where(
                    OutboundCallAttempt.customer_id == customer_id,
                    OutboundCallAttempt.org_id == org_id,
                    OutboundCallAttempt.created_at >= cutoff,
                    OutboundCallAttempt.status.notin_(("PENDING",)),
                )
            )
        ).scalar_one()
        return int(count)

    async def _has_active_consent(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
        consent_type: str = CONSENT_TYPE_OUTBOUND_CALL,
    ) -> bool:
        row = (
            await self.db.execute(
                select(ConsentRecord)
                .where(
                    ConsentRecord.customer_id == customer_id,
                    ConsentRecord.org_id == org_id,
                    ConsentRecord.consent_type == consent_type,
                    ConsentRecord.consent_given.is_(True),
                    ConsentRecord.revoked_at.is_(None),
                )
                .order_by(ConsentRecord.consented_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return row is not None

    async def check_outbound_eligibility(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
        *,
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        customer = await self.db.get(Customer, customer_id)
        if customer is None or customer.org_id != org_id:
            return {
                "eligible": False,
                "reason": "CUSTOMER_NOT_FOUND",
                "checks": {},
            }

        metadata = dict(customer.metadata_ or {})
        dnc = bool(metadata.get("dnc"))
        if dnc:
            return {
                "eligible": False,
                "reason": "DNC_REGISTERED",
                "checks": {"dnc": True},
            }

        has_consent = await self._has_active_consent(customer_id, org_id)
        attempts_30d = await self._count_recent_attempts(customer_id, org_id, max_attempts)
        phone = (customer.phone_primary or "").strip()
        phone_valid = bool(phone) and bool(normalize_phone_to_e164(phone))

        checks = {
            "dnc": False,
            "consent": has_consent,
            "attempts_30d": attempts_30d,
            "phone_valid": phone_valid,
        }

        if not has_consent:
            return {"eligible": False, "reason": "NO_CONSENT", "checks": checks}
        if attempts_30d >= max_attempts:
            return {
                "eligible": False,
                "reason": "MAX_ATTEMPTS_REACHED",
                "checks": checks,
            }
        if not phone_valid:
            return {"eligible": False, "reason": "NO_PHONE", "checks": checks}

        return {"eligible": True, "reason": "ELIGIBLE", "checks": checks}

    async def record_consent(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
        consent_type: str,
        consent_method: str,
        consent_text: str,
        *,
        call_id: str | None = None,
        consent_given: bool = True,
    ) -> ConsentRecord:
        record = ConsentRecord(
            customer_id=customer_id,
            org_id=org_id,
            consent_type=consent_type,
            consent_given=consent_given,
            consent_method=consent_method,
            consent_call_id=call_id,
            consent_text=consent_text,
            consented_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def revoke_consent(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
        consent_type: str,
        revocation_method: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        rows = (
            await self.db.execute(
                select(ConsentRecord).where(
                    ConsentRecord.customer_id == customer_id,
                    ConsentRecord.org_id == org_id,
                    ConsentRecord.consent_type == consent_type,
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        for row in rows:
            row.revoked_at = now
            row.revocation_method = revocation_method

        if revocation_method in {"SMS_STOP", "VERBAL"}:
            customer = await self.db.get(Customer, customer_id)
            if customer is not None and customer.org_id == org_id:
                metadata = dict(customer.metadata_ or {})
                metadata["dnc"] = True
                customer.metadata_ = metadata
        await self.db.flush()

    async def get_consent_status(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> dict[str, Any]:
        customer = await self.db.get(Customer, customer_id)
        if customer is None or customer.org_id != org_id:
            raise ValueError("Customer not found")

        active = (
            await self.db.execute(
                select(ConsentRecord)
                .where(
                    ConsentRecord.customer_id == customer_id,
                    ConsentRecord.org_id == org_id,
                    ConsentRecord.revoked_at.is_(None),
                )
                .order_by(ConsentRecord.consented_at.desc())
            )
        ).scalars().all()

        return {
            "customer_id": str(customer_id),
            "dnc": bool((customer.metadata_ or {}).get("dnc")),
            "active_consents": [
                {
                    "consent_id": str(r.consent_id),
                    "consent_type": r.consent_type,
                    "consent_method": r.consent_method,
                    "consented_at": r.consented_at.isoformat(),
                }
                for r in active
                if r.consent_given
            ],
        }
