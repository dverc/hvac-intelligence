"""API key authentication for dashboard REST and SSE endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.core.config import get_settings


async def verify_api_key(request: Request) -> None:
    """Require a valid dashboard API key via header or query parameter."""
    settings = get_settings()
    provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")

    if not provided or provided != settings.DASHBOARD_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


def request_has_valid_api_key(request: Request) -> bool:
    """Check API key without raising — used by OpenAPI docs middleware."""
    settings = get_settings()
    provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    return bool(provided and provided == settings.DASHBOARD_API_KEY)
