from __future__ import annotations

import logging
import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.deps import get_db, get_google_calendar_service
from app.core.config import get_settings
from app.core.tenant import get_dashboard_org_id
from app.services.google_calendar_service import GoogleCalendarService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

google_oauth_router = APIRouter(
    prefix="/api/v1/integrations/google", tags=["integrations"]
)


class GoogleDisconnectBody(BaseModel):
    google_account_email: str


class GoogleSyncBody(BaseModel):
    technician_id: uuid.UUID
    date_from: date
    date_to: date


@router.get("/google/connect")
async def google_connect(
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    technician_id: uuid.UUID | None = Query(default=None),
    gcal: GoogleCalendarService = Depends(get_google_calendar_service),
) -> dict[str, str]:
    url = gcal.get_oauth_url(org_id, technician_id)
    return {"authorization_url": url}


@google_oauth_router.get("/oauth/callback")
async def google_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    success_url = f"{base}/dashboard/integrations?connected=google&status=success"
    error_url = f"{base}/dashboard/integrations?connected=google&status=error"

    if error:
        return RedirectResponse(
            f"{error_url}&reason={quote(error)}", status_code=302
        )
    if not code or not state:
        return RedirectResponse(
            f"{error_url}&reason={quote('missing_code_or_state')}",
            status_code=302,
        )

    gcal = GoogleCalendarService(db)
    try:
        await gcal.handle_oauth_callback(code, state)
        await db.commit()
        return RedirectResponse(success_url, status_code=302)
    except Exception as exc:
        logger.exception("Google OAuth callback failed: %s", exc)
        await db.rollback()
        return RedirectResponse(
            f"{error_url}&reason={quote(str(exc)[:200])}",
            status_code=302,
        )


@router.get("/google/status")
async def google_status(
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    gcal: GoogleCalendarService = Depends(get_google_calendar_service),
) -> dict:
    calendars = await gcal.list_connected_calendars(org_id)
    return {
        "connected": len(calendars) > 0,
        "calendars": calendars,
    }


@router.delete("/google/disconnect")
async def google_disconnect(
    body: GoogleDisconnectBody,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    gcal: GoogleCalendarService = Depends(get_google_calendar_service),
) -> dict[str, bool]:
    ok = await gcal.disconnect(org_id, body.google_account_email)
    if not ok:
        raise HTTPException(status_code=404, detail="Calendar connection not found")
    return {"disconnected": True}


@router.post("/google/sync")
async def google_sync(
    body: GoogleSyncBody,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    gcal: GoogleCalendarService = Depends(get_google_calendar_service),
) -> dict[str, int]:
    count = await gcal.sync_calendar_to_availability(
        org_id,
        body.technician_id,
        body.date_from,
        body.date_to,
    )
    return {"synced": count}
