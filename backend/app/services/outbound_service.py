"""Outbound campaign orchestration with compliance-first execution."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.constants import CONSENT_TYPE_OUTBOUND_CALL
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.outbound_campaign import OutboundCallAttempt, OutboundCampaign
from app.schemas.organization import OrganizationSettings
from app.services.compliance_service import (
    ComplianceService,
    check_calling_hours,
    fetch_org_settings,
)
from app.services.sms_service import normalize_phone_to_e164
from app.services.vapi_outbound_service import VapiOutboundService

logger = logging.getLogger(__name__)


async def org_outbound_enabled(db: AsyncSession, org: Organization) -> bool:
    """Read outbound_enabled from org_settings, falling back to org.settings JSONB."""
    org_settings = await fetch_org_settings(db, org.org_id)
    if org_settings is not None:
        return bool(org_settings.outbound_enabled)
    settings = OrganizationSettings.model_validate(org.settings or {})
    return bool(settings.outbound_enabled)


class OutboundService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.compliance = ComplianceService(db)
        self.vapi = VapiOutboundService(db)

    async def _org_outbound_enabled(self, org: Organization) -> bool:
        return await org_outbound_enabled(self.db, org)

    async def _customers_above_threshold(
        self,
        org_id: uuid.UUID,
        threshold: Decimal,
    ) -> list[tuple[Customer, float | None]]:
        latest_score = (
            select(
                ChurnScore.entity_id,
                func.max(ChurnScore.score_timestamp).label("max_ts"),
            )
            .where(
                ChurnScore.org_id == org_id,
                ChurnScore.entity_type == "CUSTOMER",
            )
            .group_by(ChurnScore.entity_id)
            .subquery()
        )
        latest_churn = aliased(ChurnScore)
        rows = (
            await self.db.execute(
                select(Customer, latest_churn.churn_probability)
                .outerjoin(
                    latest_score,
                    latest_score.c.entity_id == Customer.customer_id,
                )
                .outerjoin(
                    latest_churn,
                    and_(
                        latest_churn.entity_id == Customer.customer_id,
                        latest_churn.score_timestamp == latest_score.c.max_ts,
                        latest_churn.org_id == org_id,
                    ),
                )
                .where(
                    Customer.org_id == org_id,
                    Customer.account_status == "ACTIVE",
                )
            )
        ).all()

        result: list[tuple[Customer, float | None]] = []
        threshold_f = float(threshold)
        for customer, prob in rows:
            score = float(prob) if prob is not None else float(
                (customer.metadata_ or {}).get("churn_probability", 0.0)
            )
            if score >= threshold_f:
                result.append((customer, score))
        return result

    async def count_eligible_customers(
        self,
        org_id: uuid.UUID,
        threshold: Decimal,
        max_attempts: int,
    ) -> int:
        candidates = await self._customers_above_threshold(org_id, threshold)
        count = 0
        for customer, _ in candidates:
            eligibility = await self.compliance.check_outbound_eligibility(
                customer.customer_id, org_id, max_attempts=max_attempts
            )
            if eligibility["eligible"]:
                count += 1
        return count

    async def create_campaign(
        self,
        org_id: uuid.UUID,
        campaign_data: dict[str, Any],
    ) -> OutboundCampaign:
        threshold = Decimal(str(campaign_data["churn_score_threshold"]))
        max_attempts = int(campaign_data.get("max_attempts", 2))
        campaign = OutboundCampaign(
            org_id=org_id,
            campaign_name=campaign_data["campaign_name"],
            campaign_type=campaign_data["campaign_type"],
            status="DRAFT",
            churn_score_threshold=threshold,
            max_attempts=max_attempts,
            calling_hours_start=int(campaign_data.get("calling_hours_start", 9)),
            calling_hours_end=int(campaign_data.get("calling_hours_end", 18)),
            disclosure_style=campaign_data.get("disclosure_style", "FRIENDLY"),
        )
        self.db.add(campaign)
        await self.db.flush()

        eligible = await self.count_eligible_customers(org_id, threshold, max_attempts)
        campaign.total_customers_targeted = eligible
        await self.db.flush()
        return campaign

    async def get_campaign_customers(
        self,
        campaign_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        campaign = await self.db.get(OutboundCampaign, campaign_id)
        if campaign is None or campaign.org_id != org_id:
            raise ValueError("Campaign not found")

        candidates = await self._customers_above_threshold(
            org_id, campaign.churn_score_threshold
        )
        items: list[dict[str, Any]] = []
        for customer, score in candidates:
            eligibility = await self.compliance.check_outbound_eligibility(
                customer.customer_id,
                org_id,
                max_attempts=campaign.max_attempts,
            )
            items.append(
                {
                    "customer_id": str(customer.customer_id),
                    "full_name": customer.full_name,
                    "phone_primary": customer.phone_primary,
                    "churn_probability": score,
                    "eligible": eligibility["eligible"],
                    "reason": eligibility["reason"],
                    "checks": eligibility.get("checks", {}),
                }
            )
        return items

    async def _log_blocked_attempt(
        self,
        campaign: OutboundCampaign,
        customer: Customer,
        status: str,
        notes: str | None = None,
    ) -> OutboundCallAttempt:
        phone = normalize_phone_to_e164(customer.phone_primary or "") or customer.phone_primary
        attempt = OutboundCallAttempt(
            campaign_id=campaign.campaign_id,
            customer_id=customer.customer_id,
            org_id=campaign.org_id,
            phone_number=phone or "",
            status=status,
            notes=notes,
            attempted_at=datetime.now(timezone.utc),
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def execute_campaign(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        campaign = await self.db.get(OutboundCampaign, campaign_id)
        if campaign is None:
            raise ValueError("Campaign not found")

        if campaign.status == "RUNNING":
            pass
        elif campaign.status == "ACTIVE":
            campaign.status = "RUNNING"
            await self.db.flush()
        else:
            raise HTTPException(
                status_code=400,
                detail="Campaign must be ACTIVE to execute",
            )

        org = await self.db.get(Organization, campaign.org_id)
        if org is None:
            raise ValueError("Organization not found")

        org_settings = await fetch_org_settings(self.db, campaign.org_id)
        org_timezone = org_settings.timezone if org_settings else None

        if not await self._org_outbound_enabled(org):
            campaign.status = "ACTIVE"
            await self.db.flush()
            return {
                "total_attempted": 0,
                "total_blocked": 0,
                "total_called": 0,
                "block_reasons": {"OUTBOUND_DISABLED": 1},
                "message": "Outbound calling is disabled for this organization",
            }

        candidates = await self._customers_above_threshold(
            campaign.org_id, campaign.churn_score_threshold
        )

        total_attempted = 0
        total_blocked = 0
        total_called = 0
        total_consented = 0
        block_reasons: Counter[str] = Counter()

        try:
            for customer, _score in candidates:
                total_attempted += 1
                eligibility = await self.compliance.check_outbound_eligibility(
                    customer.customer_id,
                    campaign.org_id,
                    max_attempts=campaign.max_attempts,
                )
                if not eligibility["eligible"]:
                    reason = eligibility["reason"]
                    status_map = {
                        "DNC_REGISTERED": "DNC_BLOCKED",
                        "NO_CONSENT": "CONSENT_BLOCKED",
                        "MAX_ATTEMPTS_REACHED": "CONSENT_BLOCKED",
                        "NO_PHONE": "FAILED",
                    }
                    status = status_map.get(reason, "FAILED")
                    await self._log_blocked_attempt(
                        campaign, customer, status, notes=reason
                    )
                    total_blocked += 1
                    block_reasons[reason] += 1
                    continue

                if not check_calling_hours(
                    customer.phone_primary,
                    campaign.calling_hours_start,
                    campaign.calling_hours_end,
                    org_timezone=org_timezone,
                ):
                    await self._log_blocked_attempt(
                        campaign, customer, "HOURS_BLOCKED", notes="Outside calling hours"
                    )
                    total_blocked += 1
                    block_reasons["HOURS_BLOCKED"] += 1
                    continue

                if eligibility.get("checks", {}).get("consent"):
                    total_consented += 1

                phone = normalize_phone_to_e164(customer.phone_primary or "")
                attempt = OutboundCallAttempt(
                    campaign_id=campaign.campaign_id,
                    customer_id=customer.customer_id,
                    org_id=campaign.org_id,
                    phone_number=phone,
                    status="PENDING",
                )
                self.db.add(attempt)
                await self.db.flush()

                result = await self.vapi.place_outbound_call(
                    customer, org, campaign, attempt.attempt_id
                )
                if result.get("success"):
                    total_called += 1
                    campaign.total_calls_made += 1
                else:
                    total_blocked += 1
                    block_reasons["VAPI_FAILED"] += 1

            campaign.total_consented += total_consented
            campaign.updated_at = datetime.now(timezone.utc)
            campaign.status = "ACTIVE"
            await self.db.flush()
        except Exception:
            campaign.status = "ACTIVE"
            await self.db.flush()
            raise

        return {
            "total_attempted": total_attempted,
            "total_blocked": total_blocked,
            "total_called": total_called,
            "block_reasons": dict(block_reasons),
        }

    async def list_blocked_attempts(
        self,
        org_id: uuid.UUID,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(OutboundCallAttempt, Customer.full_name)
                .join(Customer, Customer.customer_id == OutboundCallAttempt.customer_id)
                .where(
                    OutboundCallAttempt.org_id == org_id,
                    OutboundCallAttempt.status.in_(
                        ("DNC_BLOCKED", "CONSENT_BLOCKED", "HOURS_BLOCKED", "FAILED")
                    ),
                )
                .order_by(OutboundCallAttempt.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            {
                "attempt_id": str(attempt.attempt_id),
                "customer_id": str(attempt.customer_id),
                "customer_name": full_name,
                "block_reason": attempt.status,
                "notes": attempt.notes,
                "timestamp": (attempt.attempted_at or attempt.created_at).isoformat(),
            }
            for attempt, full_name in rows
        ]

    async def record_inbound_engagement_consent(
        self,
        customer_id: uuid.UUID,
        org_id: uuid.UUID,
        call_id: str,
    ) -> None:
        """Auto-record verbal inbound consent after successful engagement."""
        await self.compliance.record_consent(
            customer_id,
            org_id,
            CONSENT_TYPE_OUTBOUND_CALL,
            "VERBAL_INBOUND",
            "Customer engaged with inbound AI call without opting out",
            call_id=call_id,
        )
