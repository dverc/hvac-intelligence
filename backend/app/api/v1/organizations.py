from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.organization import Organization
from app.models.customer import Customer
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationListOut,
    OrganizationOut,
    OrganizationUpdate,
)
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge patch into a copy of base (patch wins on scalars)."""
    merged = dict(base)
    for key, value in patch.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@router.get("", response_model=list[OrganizationListOut])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationListOut]:
    counts_subq = (
        select(
            Customer.org_id,
            func.count(Customer.customer_id).label("customer_count"),
        )
        .group_by(Customer.org_id)
        .subquery()
    )
    stmt = (
        select(
            Organization,
            func.coalesce(counts_subq.c.customer_count, 0).label("customer_count"),
        )
        .outerjoin(counts_subq, Organization.org_id == counts_subq.c.org_id)
        .order_by(Organization.org_name)
    )
    rows = (await db.execute(stmt)).all()
    return [
        OrganizationListOut(
            org_id=org.org_id,
            org_name=org.org_name,
            slug=org.slug,
            industry=org.industry,
            business_phone=org.business_phone,
            vapi_assistant_id=org.vapi_assistant_id,
            vapi_phone_number_id=org.vapi_phone_number_id,
            plan_tier=org.plan_tier,
            is_active=org.is_active,
            settings=org.settings or {},
            created_at=org.created_at,
            updated_at=org.updated_at,
            customer_count=int(customer_count or 0),
        )
        for org, customer_count in rows
    ]


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
) -> Organization:
    existing_slug = (
        await db.execute(select(Organization).where(Organization.slug == body.slug))
    ).scalar_one_or_none()
    if existing_slug is not None:
        raise HTTPException(status_code=409, detail=f"slug '{body.slug}' already exists")

    if body.business_phone:
        existing_phone = (
            await db.execute(
                select(Organization).where(
                    Organization.business_phone == body.business_phone
                )
            )
        ).scalar_one_or_none()
        if existing_phone is not None:
            raise HTTPException(
                status_code=409,
                detail=f"business_phone '{body.business_phone}' already exists",
            )

    org = Organization(
        org_name=body.org_name,
        slug=body.slug,
        industry=body.industry,
        business_phone=body.business_phone,
        vapi_assistant_id=body.vapi_assistant_id,
        vapi_phone_number_id=body.vapi_phone_number_id,
        plan_tier=body.plan_tier,
        is_active=body.is_active,
        settings=body.settings.model_dump(),
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    data = body.model_dump(exclude_unset=True)
    settings_patch = data.pop("settings", None)

    if "slug" in data and data["slug"] != org.slug:
        clash = (
            await db.execute(
                select(Organization).where(Organization.slug == data["slug"])
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=409, detail="slug already exists")

    if "business_phone" in data and data["business_phone"] != org.business_phone:
        if data["business_phone"]:
            clash = (
                await db.execute(
                    select(Organization).where(
                        Organization.business_phone == data["business_phone"]
                    )
                )
            ).scalar_one_or_none()
            if clash is not None:
                raise HTTPException(
                    status_code=409, detail="business_phone already exists"
                )

    old_phone = org.business_phone
    for field, value in data.items():
        setattr(org, field, value)

    if settings_patch is not None:
        # DEEP-MERGE settings rather than replacing the whole blob.
        org.settings = _deep_merge(org.settings or {}, settings_patch)

    await db.flush()
    await db.refresh(org)

    # Tenant routing may have changed; clear cached phone->org bindings.
    tenant_service = TenantService(db)
    tenant_service.invalidate_cache(old_phone)
    if org.business_phone:
        tenant_service.invalidate_cache(org.business_phone)

    return org
