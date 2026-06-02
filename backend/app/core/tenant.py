"""Tenant scoping helpers and the dashboard org dependency.

`scoped()` is the defense-in-depth guard services should prefer when building
queries so org filtering can't be forgotten. `get_dashboard_org_id` is a
STOPGAP: it scopes every dashboard request to a single configured org until a
later phase carries the org inside the authenticated JWT.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select

from app.core.config import get_settings


def scoped(query: Select, model: type, org_id: uuid.UUID) -> Select:
    """Apply the tenant filter to a SELECT for a tenant-scoped model."""
    return query.where(model.org_id == org_id)


def get_dashboard_org_id() -> uuid.UUID:
    """FastAPI dependency: the org every dashboard query is scoped to.

    STOPGAP until JWT-based auth carries the org per-user; reads DASHBOARD_ORG_ID.
    """
    return uuid.UUID(get_settings().DASHBOARD_ORG_ID)
