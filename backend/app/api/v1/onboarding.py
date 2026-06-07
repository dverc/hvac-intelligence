from __future__ import annotations

import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.models.organization import Organization
from app.models.technician import Technician
from app.schemas.onboarding import OnboardingProvisionRequest, OnboardingProvisionResponse

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _slugify_business_name(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return (slug or "org")[:100]


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while True:
        existing = (
            await db.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()
        if existing is None:
            return slug
        suffix_slug = f"{base_slug}-{suffix}"[:100]
        slug = suffix_slug
        suffix += 1


@router.post("/provision", response_model=OnboardingProvisionResponse, status_code=201)
async def provision_onboarding(
    body: OnboardingProvisionRequest,
    db: AsyncSession = Depends(get_db),
) -> OnboardingProvisionResponse:
    if not body.business_name or not str(body.business_name).strip():
        raise HTTPException(status_code=400, detail="business_name is required")
    if not body.phone_number or not str(body.phone_number).strip():
        raise HTTPException(status_code=400, detail="phone_number is required")

    existing_phone = (
        await db.execute(
            select(Organization).where(
                Organization.business_phone == body.phone_number
            )
        )
    ).scalar_one_or_none()
    if existing_phone is not None:
        raise HTTPException(
            status_code=409,
            detail=f"phone_number '{body.phone_number}' already exists",
        )

    slug = await _unique_slug(db, _slugify_business_name(body.business_name))

    settings: dict = {
        "timezone": body.timezone,
        "business_hours": {
            day: (hours.model_dump() if hours is not None else None)
            for day, hours in body.business_hours.items()
        },
        "notification_email": body.notification_email,
        "trade_type": body.trade_type,
        "pinecone_namespace": "faq_general",
    }
    if body.service_zip_codes:
        settings["service_area"] = {"zip_codes": body.service_zip_codes}

    org = Organization(
        org_name=body.business_name.strip(),
        slug=slug,
        industry=body.trade_type,
        business_phone=body.phone_number,
        vapi_phone_number=body.phone_number,
        agent_name=body.agent_name.strip(),
        plan_tier="starter",
        settings=settings,
    )
    db.add(org)
    await db.flush()

    db.add(
        Technician(
            org_id=org.org_id,
            employee_number="ON-CALL-1",
            full_name="On-Call Tech",
            hire_date=date.today(),
            employment_status="ACTIVE",
        )
    )
    await db.flush()
    await db.refresh(org)

    settings_obj = get_settings()
    # Per-org API keys are a Phase 12 feature; reuse the global dashboard key for now.
    return OnboardingProvisionResponse(
        org_id=org.org_id,
        org_name=org.org_name,
        slug=org.slug,
        agent_name=org.agent_name or body.agent_name,
        dashboard_api_key=settings_obj.DASHBOARD_API_KEY,
    )
