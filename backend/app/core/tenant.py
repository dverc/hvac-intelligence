"""Tenant scoping helpers and the dashboard org dependency."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import Select

from app.core.auth_jwt import get_current_user
from app.core.config import get_settings


def scoped(query: Select, model: type, org_id: uuid.UUID) -> Select:
    """Apply the tenant filter to a SELECT for a tenant-scoped model."""
    return query.where(model.org_id == org_id)


async def get_dashboard_org_id(
    current_user: dict = Depends(get_current_user),
) -> uuid.UUID:
    """FastAPI dependency: org scope from the authenticated JWT."""
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization not found in token",
        )
    try:
        return uuid.UUID(str(org_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid organization in token",
        ) from exc


def get_fallback_dashboard_org_id() -> uuid.UUID:
    """Non-auth fallback for webhooks and background jobs (env-configured org)."""
    return uuid.UUID(get_settings().DASHBOARD_ORG_ID)
