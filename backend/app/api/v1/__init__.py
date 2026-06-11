from fastapi import APIRouter, Depends

from app.core.auth_jwt import get_current_user

from app.api.v1 import (
    admin,
    analytics,
    audit,
    auth,
    calls,
    churn,
    customers,
    imports,
    integrations,
    knowledge,
    ml,
    onboarding,
    organizations,
    outbound,
    portal,
    scheduling,
    stream,
    system,
    webhook_vapi,
)
_jwt_auth = [Depends(get_current_user)]

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(portal.router)
api_router.include_router(admin.router, dependencies=_jwt_auth)
api_router.include_router(organizations.router, dependencies=_jwt_auth)
api_router.include_router(onboarding.router, dependencies=_jwt_auth)
api_router.include_router(calls.router, dependencies=_jwt_auth)
api_router.include_router(customers.router, dependencies=_jwt_auth)
api_router.include_router(churn.router, dependencies=_jwt_auth)
api_router.include_router(ml.router, dependencies=_jwt_auth)
api_router.include_router(knowledge.router, dependencies=_jwt_auth)
api_router.include_router(imports.router, dependencies=_jwt_auth)
api_router.include_router(system.router, dependencies=_jwt_auth)
api_router.include_router(audit.router, dependencies=_jwt_auth)
api_router.include_router(scheduling.router, dependencies=_jwt_auth)
api_router.include_router(integrations.router, dependencies=_jwt_auth)
api_router.include_router(analytics.router, dependencies=_jwt_auth)
api_router.include_router(outbound.router, dependencies=_jwt_auth)
api_router.include_router(stream.router, dependencies=_jwt_auth)

vapi_router = webhook_vapi.router
google_oauth_router = integrations.google_oauth_router
jobber_oauth_router = integrations.jobber_oauth_router
