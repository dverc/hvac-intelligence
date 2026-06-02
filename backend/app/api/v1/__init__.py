from fastapi import APIRouter, Depends

from app.api.v1 import (
    analytics,
    calls,
    churn,
    customers,
    organizations,
    stream,
    webhook_vapi,
)
from app.core.tenant import get_dashboard_org_id

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(organizations.router)
api_router.include_router(calls.router)
api_router.include_router(customers.router)
api_router.include_router(churn.router)
# TENANT-TODO: analytics aggregation SQL is not yet org-filtered; the dependency
# below scopes the request to a valid org as a stopgap (single-tenant dev today).
api_router.include_router(
    analytics.router, dependencies=[Depends(get_dashboard_org_id)]
)
api_router.include_router(stream.router)

vapi_router = webhook_vapi.router
