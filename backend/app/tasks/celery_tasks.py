"""Celery tasks for outbound campaign execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.organization import Organization
from app.models.outbound_campaign import OutboundCampaign
from app.pipeline.celery_app import celery_app
from app.schemas.organization import OrganizationSettings
from app.services.compliance_service import check_calling_hours
from app.services.outbound_service import OutboundService

logger = logging.getLogger(__name__)

_TRANSIENT_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)

try:
    import httpx

    _TRANSIENT_EXCEPTIONS = _TRANSIENT_EXCEPTIONS + (
        httpx.HTTPError,
        httpx.TimeoutException,
    )
except ImportError:  # pragma: no cover
    pass

try:
    from sqlalchemy.exc import OperationalError

    _TRANSIENT_EXCEPTIONS = _TRANSIENT_EXCEPTIONS + (OperationalError,)
except ImportError:  # pragma: no cover
    pass

_OUTBOUND_RETRY = dict(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)


async def _execute_campaign_async(campaign_id: uuid.UUID) -> dict:
    async with get_session_factory()() as session:
        try:
            service = OutboundService(session)
            result = await service.execute_campaign(campaign_id)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


@celery_app.task(name="app.tasks.celery_tasks.execute_outbound_campaign", **_OUTBOUND_RETRY)
def execute_outbound_campaign(self, campaign_id: str) -> dict:
    """Execute an outbound campaign with compliance checks on every dial."""
    cid = uuid.UUID(campaign_id)
    try:
        result = asyncio.run(_execute_campaign_async(cid))
        logger.info(
            "Outbound campaign executed | campaign_id=%s | called=%s | blocked=%s",
            campaign_id,
            result.get("total_called"),
            result.get("total_blocked"),
        )
        return result
    except _TRANSIENT_EXCEPTIONS as exc:
        logger.warning("Outbound campaign transient failure | campaign_id=%s", campaign_id)
        raise self.retry(exc=exc) from exc


async def _launch_active_campaigns_async() -> dict:
    launched = 0
    skipped_hours = 0
    async with get_session_factory()() as session:
        campaigns = (
            await session.execute(
                select(OutboundCampaign).where(OutboundCampaign.status == "ACTIVE")
            )
        ).scalars().all()
        for campaign in campaigns:
            org = await session.get(Organization, campaign.org_id)
            if org is None:
                continue
            settings = OrganizationSettings.model_validate(org.settings or {})
            if not settings.outbound_enabled:
                continue
            phone = org.business_phone or ""
            if phone and not check_calling_hours(
                phone,
                campaign.calling_hours_start,
                campaign.calling_hours_end,
            ):
                skipped_hours += 1
                continue
            execute_outbound_campaign.delay(str(campaign.campaign_id))
            launched += 1
        await session.commit()
    return {"launched": launched, "skipped_hours": skipped_hours}


@celery_app.task(name="app.tasks.celery_tasks.check_and_launch_campaigns", **_OUTBOUND_RETRY)
def check_and_launch_campaigns(self) -> dict:
    """Daily launcher for ACTIVE outbound campaigns (respects calling hours)."""
    try:
        result = asyncio.run(_launch_active_campaigns_async())
        logger.info(
            "Outbound campaign launcher | launched=%s | skipped_hours=%s at %s",
            result["launched"],
            result["skipped_hours"],
            datetime.now(timezone.utc).isoformat(),
        )
        return result
    except _TRANSIENT_EXCEPTIONS as exc:
        raise self.retry(exc=exc) from exc
