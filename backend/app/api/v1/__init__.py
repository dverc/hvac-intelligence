from fastapi import APIRouter

from app.api.v1 import analytics, calls, churn, customers, stream, webhook_vapi

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(calls.router)
api_router.include_router(customers.router)
api_router.include_router(churn.router)
api_router.include_router(analytics.router)
api_router.include_router(stream.router)

vapi_router = webhook_vapi.router
