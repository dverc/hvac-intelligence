from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import decrypt_token, encrypt_token
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.google_calendar_token import GoogleCalendarToken
from app.models.organization import Organization
from app.models.technician import Technician
from app.schemas.organization import OrganizationSettings
from app.services.availability_service import AvailabilityService
from app.services.google_oauth_state import OAuthStateError, build_oauth_state, verify_oauth_state

logger = logging.getLogger(__name__)

_PRIORITY_COLOR = {"P1": "11", "P2": "6", "P3": "2", "P4": "2"}


class GoogleCalendarService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.availability = AvailabilityService(db)

    def _client_config(self) -> dict[str, Any]:
        return {
            "web": {
                "client_id": self.settings.GOOGLE_CLIENT_ID,
                "client_secret": self.settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.GOOGLE_OAUTH_REDIRECT_URI],
            }
        }

    def get_oauth_url(
        self, org_id: uuid.UUID, technician_id: uuid.UUID | None = None
    ) -> str:
        state = build_oauth_state(
            org_id, technician_id, self.settings.DASHBOARD_API_KEY
        )
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self.settings.GOOGLE_CALENDAR_SCOPES,
            redirect_uri=self.settings.GOOGLE_OAUTH_REDIRECT_URI,
            autogenerate_code_verifier=False,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url

    async def handle_oauth_callback(self, code: str, state: str) -> GoogleCalendarToken:
        try:
            org_id, technician_id = verify_oauth_state(
                state, self.settings.DASHBOARD_API_KEY
            )
        except OAuthStateError as exc:
            raise ValueError(str(exc)) from exc

        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self.settings.GOOGLE_CALENDAR_SCOPES,
            redirect_uri=self.settings.GOOGLE_OAUTH_REDIRECT_URI,
            autogenerate_code_verifier=False,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        if not credentials.token:
            raise ValueError("OAuth token exchange did not return an access token")

        email = self._resolve_account_email(flow)
        expiry = self._expiry_for_db(credentials.expiry)

        existing = (
            await self.db.execute(
                select(GoogleCalendarToken).where(
                    GoogleCalendarToken.org_id == org_id,
                    GoogleCalendarToken.google_account_email == email,
                )
            )
        ).scalar_one_or_none()

        if existing:
            row = existing
            row.technician_id = technician_id
            row.access_token = encrypt_token(credentials.token) or ""
            row.refresh_token = encrypt_token(credentials.refresh_token)
            row.token_expiry = expiry
            row.scopes = " ".join(credentials.scopes or [])
            row.is_active = True
            row.calendar_id = row.calendar_id or "primary"
        else:
            row = GoogleCalendarToken(
                org_id=org_id,
                technician_id=technician_id,
                google_account_email=email,
                calendar_id="primary",
                access_token=encrypt_token(credentials.token) or "",
                refresh_token=encrypt_token(credentials.refresh_token),
                token_expiry=expiry,
                scopes=" ".join(credentials.scopes or []),
                is_active=True,
            )
            self.db.add(row)

        await self.db.flush()
        return row

    def _resolve_account_email(self, flow: Flow) -> str:
        """Resolve Google account email from OAuth flow credentials (server-side)."""
        credentials = flow.credentials
        self._normalize_credentials_expiry(credentials)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._normalize_credentials_expiry(credentials)

        if credentials.id_token:
            try:
                from google.oauth2 import id_token

                info = id_token.verify_oauth2_token(
                    credentials.id_token,
                    Request(),
                    self.settings.GOOGLE_CLIENT_ID,
                )
                email = info.get("email")
                if email:
                    return str(email)
            except Exception as exc:
                logger.warning("id_token email lookup failed: %s", exc)

        oauth2_service = build(
            "oauth2", "v2", credentials=credentials, cache_discovery=False
        )
        user_info = oauth2_service.userinfo().get().execute()
        email = user_info.get("email")
        if not email:
            raise ValueError("Could not determine Google account email")
        return str(email)

    async def _get_token_row(
        self, org_id: uuid.UUID, technician_id: uuid.UUID | None = None
    ) -> GoogleCalendarToken | None:
        stmt = select(GoogleCalendarToken).where(
            GoogleCalendarToken.org_id == org_id,
            GoogleCalendarToken.is_active.is_(True),
        )
        if technician_id:
            stmt = stmt.where(
                (GoogleCalendarToken.technician_id == technician_id)
                | (GoogleCalendarToken.technician_id.is_(None))
            ).order_by(
                GoogleCalendarToken.technician_id.desc().nullslast()
            )
        else:
            stmt = stmt.where(GoogleCalendarToken.technician_id.is_(None))
        return (await self.db.execute(stmt.limit(1))).scalar_one_or_none()

    async def has_active_connection(self, org_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(GoogleCalendarToken.token_id).where(
                GoogleCalendarToken.org_id == org_id,
                GoogleCalendarToken.is_active.is_(True),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _normalize_credentials_expiry(credentials: Credentials) -> None:
        """google-auth compares expiry to naive UTC; DB tokens are often aware."""
        if credentials.expiry is None:
            return
        if credentials.expiry.tzinfo is not None:
            credentials.expiry = credentials.expiry.astimezone(timezone.utc).replace(
                tzinfo=None
            )

    @staticmethod
    def _expiry_for_db(expiry: datetime | None) -> datetime | None:
        if expiry is None:
            return None
        if expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry.astimezone(timezone.utc)

    def _build_credentials(self, row: GoogleCalendarToken) -> Credentials:
        token = decrypt_token(row.access_token)
        refresh = decrypt_token(row.refresh_token)
        expiry = row.token_expiry
        if expiry is not None and expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
        credentials = Credentials(
            token=token,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.GOOGLE_CLIENT_ID,
            client_secret=self.settings.GOOGLE_CLIENT_SECRET,
            scopes=self.settings.GOOGLE_CALENDAR_SCOPES,
            expiry=expiry,
        )
        self._normalize_credentials_expiry(credentials)
        return credentials

    async def get_calendar_service(
        self, org_id: uuid.UUID, technician_id: uuid.UUID | None = None
    ):
        row = await self._get_token_row(org_id, technician_id)
        if row is None:
            raise ValueError("No Google Calendar connected for this organization")

        credentials = self._build_credentials(row)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._normalize_credentials_expiry(credentials)
            row.access_token = encrypt_token(credentials.token) or ""
            row.token_expiry = self._expiry_for_db(credentials.expiry)
            await self.db.flush()

        return build("calendar", "v3", credentials=credentials, cache_discovery=False), row

    async def _org_timezone(self, org_id: uuid.UUID) -> str:
        org = await self.db.get(Organization, org_id)
        if org is None:
            return "America/Los_Angeles"
        settings = OrganizationSettings.model_validate(org.settings or {})
        return settings.timezone

    def _format_customer_address(self, customer: Customer) -> str:
        parts = [
            customer.address_line1,
            customer.address_line2,
            customer.city,
            customer.state,
            customer.zip,
        ]
        return ", ".join(p for p in parts if p)

    def _event_body(
        self,
        dispatch_job: DispatchJob,
        technician: Technician,
        customer: Customer,
        tz_name: str,
    ) -> dict[str, Any]:
        start = dispatch_job.scheduled_window_start
        end = dispatch_job.scheduled_window_end
        if start is None or end is None:
            raise ValueError("Dispatch job missing scheduled window")

        description = (
            f"Job: {dispatch_job.job_number}\n"
            f"Customer: {customer.full_name}\n"
            f"Phone: {customer.phone_primary}\n"
            f"Address: {self._format_customer_address(customer)}\n"
            f"Issue: {dispatch_job.issue_description or ''}\n"
            f"Priority: {dispatch_job.priority}"
        )
        attendees = []
        if technician.email:
            attendees.append({"email": technician.email})

        return {
            "summary": f"{dispatch_job.issue_type} — {customer.full_name}",
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end.isoformat(), "timeZone": tz_name},
            "attendees": attendees,
            "colorId": _PRIORITY_COLOR.get(dispatch_job.priority, "2"),
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 60},
                    {"method": "popup", "minutes": 30},
                ],
            },
        }

    async def create_calendar_event(
        self,
        org_id: uuid.UUID,
        dispatch_job: DispatchJob,
        technician: Technician,
        customer: Customer,
    ) -> str:
        service, token_row = await self.get_calendar_service(
            org_id, technician.technician_id
        )
        tz_name = await self._org_timezone(org_id)
        body = self._event_body(dispatch_job, technician, customer, tz_name)
        created = (
            service.events()
            .insert(calendarId=token_row.calendar_id, body=body)
            .execute()
        )
        return str(created["id"])

    async def update_calendar_event(
        self,
        org_id: uuid.UUID,
        event_id: str,
        dispatch_job: DispatchJob,
        technician: Technician,
        customer: Customer,
    ) -> bool:
        service, token_row = await self.get_calendar_service(
            org_id, technician.technician_id
        )
        tz_name = await self._org_timezone(org_id)
        body = self._event_body(dispatch_job, technician, customer, tz_name)
        service.events().update(
            calendarId=token_row.calendar_id,
            eventId=event_id,
            body=body,
        ).execute()
        return True

    async def delete_calendar_event(self, org_id: uuid.UUID, event_id: str) -> bool:
        service, token_row = await self.get_calendar_service(org_id)
        service.events().delete(
            calendarId=token_row.calendar_id, eventId=event_id
        ).execute()
        return True

    async def sync_calendar_to_availability(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> int:
        service, token_row = await self.get_calendar_service(org_id, technician_id)
        tz = ZoneInfo(await self._org_timezone(org_id))
        time_min = datetime.combine(date_from, time.min, tzinfo=tz).isoformat()
        time_max = datetime.combine(
            date_to + timedelta(days=1), time.min, tzinfo=tz
        ).isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=token_row.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = events_result.get("items", [])
        synced = 0

        for item in items:
            description = item.get("description") or ""
            if "Job: DX-" in description:
                continue

            start = item.get("start", {})
            if "date" in start:
                override_date = date.fromisoformat(start["date"])
                await self.availability.add_override(
                    org_id,
                    technician_id,
                    override_date,
                    "day_off",
                    reason=f"Google Calendar: {item.get('summary', 'Blocked')}",
                )
                synced += 1
                continue

            if "dateTime" not in start:
                continue

            start_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
            end_raw = item.get("end", {}).get("dateTime")
            end_dt = (
                datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                if end_raw
                else start_dt + timedelta(hours=1)
            )
            start_local = start_dt.astimezone(tz)
            end_local = end_dt.astimezone(tz)
            override_date = start_local.date()
            await self.availability.add_override(
                org_id,
                technician_id,
                override_date,
                "custom_hours",
                start_time=start_local.time(),
                end_time=end_local.time(),
                reason=f"Google Calendar: {item.get('summary', 'Busy')}",
            )
            synced += 1

        return synced

    async def list_connected_calendars(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(GoogleCalendarToken).where(
                    GoogleCalendarToken.org_id == org_id,
                    GoogleCalendarToken.is_active.is_(True),
                )
            )
        ).scalars().all()
        return [
            {
                "token_id": str(row.token_id),
                "email": row.google_account_email,
                "calendar_id": row.calendar_id,
                "technician_id": str(row.technician_id) if row.technician_id else None,
                "is_active": row.is_active,
                "token_expiry": row.token_expiry.isoformat() if row.token_expiry else None,
            }
            for row in rows
        ]

    async def disconnect(self, org_id: uuid.UUID, google_account_email: str) -> bool:
        row = (
            await self.db.execute(
                select(GoogleCalendarToken).where(
                    GoogleCalendarToken.org_id == org_id,
                    GoogleCalendarToken.google_account_email == google_account_email,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.is_active = False
        await self.db.flush()
        return True
