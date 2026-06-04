from fastapi import APIRouter, Depends

from app.api.v1 import (
    analytics,
    calls,
    churn,
    customers,
    integrations,
    knowledge,
    organizations,
    scheduling,
    stream,
    webhook_vapi,
)
from app.core.tenant import get_dashboard_org_id

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(organizations.router)
api_router.include_router(calls.router)
api_router.include_router(customers.router)
api_router.include_router(churn.router)
api_router.include_router(knowledge.router)
api_router.include_router(scheduling.router)
api_router.include_router(integrations.router)
api_router.include_router(
    analytics.router, dependencies=[Depends(get_dashboard_org_id)]
)
api_router.include_router(stream.router)

vapi_router = webhook_vapi.router
google_oauth_router = integrations.google_oauth_router
