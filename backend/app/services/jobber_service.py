from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import decrypt_token, encrypt_token
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.jobber_token import JobberToken
from app.models.technician import Technician
from app.services.google_oauth_state import OAuthStateError, build_oauth_state, verify_oauth_state

logger = logging.getLogger(__name__)

JOBBER_AUTHORIZE_URL = "https://api.getjobber.com/api/oauth/authorize"
JOBBER_TOKEN_URL = "https://api.getjobber.com/api/oauth/token"
JOBBER_GRAPHQL_URL = "https://api.getjobber.com/api/graphql"
JOBBER_GRAPHQL_VERSION = "2025-04-16"

ACCOUNT_INFO_QUERY = """
query {
  account {
    id
    name
    email
  }
}
"""

CLIENTS_QUERY = """
query GetClients($after: String) {
  clients(first: 50, after: $after) {
    nodes {
      id
      name
      firstName
      lastName
      emails { address primary }
      phones { number primary }
      billingAddress {
        street1
        street2
        city
        province
        postalCode
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

JOBS_QUERY = """
query GetJobs($after: String, $from: ISO8601DateTime!, $to: ISO8601DateTime!) {
  jobs(first: 50, after: $after, filter: {
    startsBetween: { from: $from, to: $to }
  }) {
    nodes {
      id
      jobNumber
      title
      status
      startAt
      endAt
      client { id name }
      assignedTo { id name }
      jobType
      instructions
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

USERS_QUERY = """
query GetUsers {
  users {
    nodes {
      id
      name { first last }
      email { raw }
      status
    }
  }
}
"""

CREATE_JOB_MUTATION = """
mutation CreateJob($input: JobCreateInput!) {
  jobCreate(input: $input) {
    job {
      id
      jobNumber
    }
    userErrors { message path }
  }
}
"""

_JOBBER_CANCELLED = frozenset(
    {"cancelled", "canceled", "archived", "closed", "completed"}
)


def _jobber_external_id(prefix: str, raw_id: str) -> str:
    return f"{prefix}:{raw_id}"[:64]


def _parse_jobber_external_id(external_id: str | None, prefix: str) -> str | None:
    if not external_id:
        return None
    needle = f"{prefix}:"
    if external_id.startswith(needle):
        return external_id[len(needle) :]
    return None


class JobberService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    def get_oauth_url(self, org_id: uuid.UUID) -> str:
        state = build_oauth_state(org_id, None, self.settings.DASHBOARD_API_KEY)
        params = {
            "client_id": self.settings.JOBBER_CLIENT_ID,
            "redirect_uri": self.settings.JOBBER_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
        return f"{JOBBER_AUTHORIZE_URL}?{urlencode(params)}"

    async def _exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                JOBBER_TOKEN_URL,
                data={
                    "client_id": self.settings.JOBBER_CLIENT_ID,
                    "client_secret": self.settings.JOBBER_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": self.settings.JOBBER_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    async def _refresh_token_request(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                JOBBER_TOKEN_URL,
                data={
                    "client_id": self.settings.JOBBER_CLIENT_ID,
                    "client_secret": self.settings.JOBBER_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    def _token_expiry_from_response(self, payload: dict[str, Any]) -> datetime | None:
        expires_in = payload.get("expires_in")
        if expires_in is None:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    @staticmethod
    def _graphql_headers(access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": JOBBER_GRAPHQL_VERSION,
        }

    async def _graphql_request(
        self,
        access_token: str,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a GraphQL request with an explicit bearer token (OAuth callback safe)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                JOBBER_GRAPHQL_URL,
                json={"query": query, "variables": variables or {}},
                headers=self._graphql_headers(access_token),
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    raise HTTPException(status_code=401, detail="Jobber API unauthorized") from exc
                raise
            payload = response.json()

        if payload.get("errors"):
            logger.error("Jobber GraphQL errors: %s", payload["errors"])
            raise ValueError(f"Jobber GraphQL error: {payload['errors']}")
        return payload

    async def handle_oauth_callback(self, code: str, state: str) -> JobberToken:
        try:
            org_id, _ = verify_oauth_state(state, self.settings.DASHBOARD_API_KEY)
        except OAuthStateError as exc:
            raise ValueError(str(exc)) from exc

        token_payload = await self._exchange_code(code)
        access_token = str(token_payload.get("access_token") or "").strip()
        refresh_token = str(token_payload.get("refresh_token") or "").strip()
        if not access_token or not refresh_token:
            raise ValueError("Jobber token exchange did not return access/refresh tokens")

        # Fresh OAuth access token only — never DB-backed auth during callback.
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.getjobber.com/api/graphql",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-JOBBER-GRAPHQL-VERSION": JOBBER_GRAPHQL_VERSION,
                },
                json={"query": ACCOUNT_INFO_QUERY},
            )
            resp.raise_for_status()
            account_info = resp.json()
            account = account_info.get("data", {}).get("account", {})
            jobber_account_id = str(account.get("id", ""))
            jobber_account_name = account.get("name", "")

        row = await self._get_token_row(org_id, active_only=False)
        expiry = self._token_expiry_from_response(token_payload)
        if row is None:
            row = JobberToken(
                org_id=org_id,
                access_token=encrypt_token(access_token) or "",
                refresh_token=encrypt_token(refresh_token) or "",
                token_expiry=expiry,
                scopes=token_payload.get("scope"),
                is_active=True,
            )
            self.db.add(row)
        else:
            row.access_token = encrypt_token(access_token) or ""
            row.refresh_token = encrypt_token(refresh_token) or ""
            row.token_expiry = expiry
            row.scopes = token_payload.get("scope")
            row.is_active = True

        row.jobber_account_id = jobber_account_id or None
        row.jobber_account_name = jobber_account_name or None
        await self.db.flush()
        return row

    async def _get_token_row(
        self, org_id: uuid.UUID, *, active_only: bool = True
    ) -> JobberToken | None:
        stmt = select(JobberToken).where(JobberToken.org_id == org_id)
        if active_only:
            stmt = stmt.where(JobberToken.is_active.is_(True))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def has_active_connection(self, org_id: uuid.UUID) -> bool:
        return await self._get_token_row(org_id) is not None

    async def refresh_access_token(self, token: JobberToken) -> JobberToken:
        refresh = decrypt_token(token.refresh_token)
        if not refresh:
            raise ValueError("Missing Jobber refresh token")

        payload = await self._refresh_token_request(refresh)
        access = payload.get("access_token")
        new_refresh = payload.get("refresh_token") or refresh
        if not access:
            raise ValueError("Jobber refresh did not return an access token")

        token.access_token = encrypt_token(access) or ""
        token.refresh_token = encrypt_token(new_refresh) or ""
        token.token_expiry = self._token_expiry_from_response(payload)
        await self.db.flush()
        return token

    def _token_needs_refresh(self, token: JobberToken) -> bool:
        if token.token_expiry is None:
            return False
        expiry = token.token_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= datetime.now(timezone.utc) + timedelta(minutes=5)

    async def _ensure_fresh_token(self, org_id: uuid.UUID) -> JobberToken:
        token = await self._get_token_row(org_id)
        if token is None:
            raise ValueError("No Jobber connection for this organization")
        if self._token_needs_refresh(token):
            token = await self.refresh_access_token(token)
        return token

    async def get_authenticated_client(self, org_id: uuid.UUID) -> httpx.AsyncClient:
        token = await self._ensure_fresh_token(org_id)
        access = decrypt_token(token.access_token)
        if not access:
            raise ValueError("Missing Jobber access token")
        return httpx.AsyncClient(
            headers=self._graphql_headers(access),
            timeout=30.0,
        )

    async def graphql_query(
        self, org_id: uuid.UUID, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        token = await self._ensure_fresh_token(org_id)
        access = decrypt_token(token.access_token)
        if not access:
            raise ValueError("Missing Jobber access token")
        return await self._graphql_request(access, query, variables)

    async def get_connection_status(self, org_id: uuid.UUID) -> dict[str, Any]:
        token = await self._get_token_row(org_id)
        if token is None:
            return {
                "connected": False,
                "account_name": None,
                "account_id": None,
                "last_sync_at": None,
                "is_active": False,
            }
        last_sync = token.last_sync_at
        return {
            "connected": True,
            "account_name": token.jobber_account_name,
            "account_id": token.jobber_account_id,
            "last_sync_at": last_sync.isoformat() if last_sync else None,
            "is_active": token.is_active,
        }

    async def mark_sync_completed(self, org_id: uuid.UUID) -> None:
        token = await self._get_token_row(org_id)
        if token:
            token.last_sync_at = datetime.now(timezone.utc)
            await self.db.flush()

    async def disconnect(self, org_id: uuid.UUID) -> bool:
        token = await self._get_token_row(org_id, active_only=False)
        if token is None:
            return False
        token.is_active = False
        await self.db.flush()
        return True

    def _primary_email(self, client: dict[str, Any]) -> str | None:
        for item in client.get("emails") or []:
            if item.get("primary"):
                return item.get("address")
        emails = client.get("emails") or []
        return emails[0].get("address") if emails else None

    def _primary_phone(self, client: dict[str, Any]) -> str | None:
        for item in client.get("phones") or []:
            if item.get("primary"):
                return item.get("number")
        phones = client.get("phones") or []
        return phones[0].get("number") if phones else None

    def _client_full_name(self, client: dict[str, Any]) -> str:
        first = (client.get("firstName") or "").strip()
        last = (client.get("lastName") or "").strip()
        if first or last:
            return f"{first} {last}".strip()
        return str(client.get("name") or "Jobber Client")

    async def sync_clients_to_customers(self, org_id: uuid.UUID) -> int:
        synced = 0
        cursor: str | None = None
        while True:
            payload = await self.graphql_query(
                org_id, CLIENTS_QUERY, {"after": cursor}
            )
            clients_block = (payload.get("data") or {}).get("clients") or {}
            nodes = clients_block.get("nodes") or []
            for client in nodes:
                jobber_id = client.get("id")
                if not jobber_id:
                    continue
                external_id = _jobber_external_id("jobber", str(jobber_id))
                existing = (
                    await self.db.execute(
                        select(Customer).where(
                            Customer.org_id == org_id,
                            Customer.external_id == external_id,
                        )
                    )
                ).scalar_one_or_none()

                addr = client.get("billingAddress") or {}
                phone = self._primary_phone(client) or "+10000000000"
                if existing:
                    existing.full_name = self._client_full_name(client)
                    existing.email = self._primary_email(client)
                    existing.phone_primary = phone
                    existing.address_line1 = addr.get("street1")
                    existing.address_line2 = addr.get("street2")
                    existing.city = addr.get("city")
                    existing.state = (addr.get("province") or "")[:2] or None
                    existing.zip = addr.get("postalCode")
                else:
                    self.db.add(
                        Customer(
                            org_id=org_id,
                            external_id=external_id,
                            full_name=self._client_full_name(client),
                            phone_primary=phone,
                            email=self._primary_email(client),
                            address_line1=addr.get("street1"),
                            address_line2=addr.get("street2"),
                            city=addr.get("city"),
                            state=(addr.get("province") or "")[:2] or None,
                            zip=addr.get("postalCode"),
                            customer_since=date.today(),
                            account_status="ACTIVE",
                            contract_type="RESIDENTIAL_OTC",
                        )
                    )
                synced += 1

            page_info = clients_block.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        await self.db.flush()
        return synced

    async def _find_technician_by_jobber_id(
        self, org_id: uuid.UUID, jobber_user_id: str
    ) -> Technician | None:
        external_id = _jobber_external_id("jobber", jobber_user_id)
        match = (
            await self.db.execute(
                select(Technician).where(
                    Technician.org_id == org_id,
                    Technician.external_id == external_id,
                )
            )
        ).scalar_one_or_none()
        if match:
            return match

        techs = (
            await self.db.execute(
                select(Technician).where(Technician.org_id == org_id)
            )
        ).scalars().all()
        for tech in techs:
            meta = tech.metadata_ or {}
            if meta.get("jobber_user_id") == jobber_user_id:
                return tech
            if tech.employee_number == f"JB-{jobber_user_id}"[:30]:
                return tech
        return None

    async def sync_users_to_technicians(self, org_id: uuid.UUID) -> int:
        payload = await self.graphql_query(org_id, USERS_QUERY)
        users_block = (payload.get("data") or {}).get("users") or {}
        nodes = users_block.get("nodes") or []
        synced = 0
        for user in nodes:
            if str(user.get("status", "")).upper() not in {"ACTIVE", "ACTIVATED"}:
                continue
            jobber_id = user.get("id")
            if not jobber_id:
                continue
            jobber_id = str(jobber_id)
            name = user.get("name") or {}
            full_name = f"{name.get('first', '')} {name.get('last', '')}".strip() or "Jobber User"
            email = (user.get("email") or {}).get("raw")

            external_id = _jobber_external_id("jobber", jobber_id)
            existing = await self._find_technician_by_jobber_id(org_id, jobber_id)
            if existing:
                existing.full_name = full_name
                existing.email = email
                existing.external_id = external_id
                meta = dict(existing.metadata_ or {})
                meta["jobber_user_id"] = jobber_id
                existing.metadata_ = meta
            else:
                self.db.add(
                    Technician(
                        org_id=org_id,
                        employee_number=f"JB-{jobber_id}"[:30],
                        external_id=external_id,
                        full_name=full_name,
                        email=email,
                        hire_date=date.today(),
                        employment_status="ACTIVE",
                        metadata_={"jobber_user_id": jobber_id},
                    )
                )
            synced += 1

        await self.db.flush()
        return synced

    def _map_jobber_status(self, status: str | None) -> str:
        if not status:
            return "SCHEDULED"
        normalized = status.lower()
        if normalized in _JOBBER_CANCELLED:
            return "CANCELLED"
        if normalized in {"in_progress", "in progress", "started"}:
            return "IN_PROGRESS"
        if normalized in {"completed", "done"}:
            return "COMPLETED"
        return "SCHEDULED"

    async def sync_jobs_to_dispatch(self, org_id: uuid.UUID, days_ahead: int = 7) -> int:
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)
        synced = 0
        cursor: str | None = None
        variables = {
            "after": cursor,
            "from": now.isoformat(),
            "to": end.isoformat(),
        }

        while True:
            variables["after"] = cursor
            payload = await self.graphql_query(org_id, JOBS_QUERY, variables)
            jobs_block = (payload.get("data") or {}).get("jobs") or {}
            nodes = jobs_block.get("nodes") or []

            for job in nodes:
                jobber_id = job.get("id")
                if not jobber_id:
                    continue
                external_job_id = f"jobber:{jobber_id}"
                status = self._map_jobber_status(job.get("status"))

                existing = (
                    await self.db.execute(
                        select(DispatchJob).where(
                            DispatchJob.org_id == org_id,
                            DispatchJob.external_job_id == external_job_id,
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.job_status = status
                    if job.get("startAt"):
                        existing.scheduled_window_start = datetime.fromisoformat(
                            str(job["startAt"]).replace("Z", "+00:00")
                        )
                    if job.get("endAt"):
                        existing.scheduled_window_end = datetime.fromisoformat(
                            str(job["endAt"]).replace("Z", "+00:00")
                        )
                    synced += 1
                    continue

                if status == "CANCELLED":
                    continue

                client = job.get("client") or {}
                client_external = _jobber_external_id("jobber", str(client.get("id", "")))
                customer = (
                    await self.db.execute(
                        select(Customer).where(
                            Customer.org_id == org_id,
                            Customer.external_id == client_external,
                        )
                    )
                ).scalar_one_or_none()
                if customer is None:
                    continue

                technician = None
                assigned = job.get("assignedTo") or {}
                if assigned.get("id"):
                    technician = await self._find_technician_by_jobber_id(
                        org_id, str(assigned["id"])
                    )

                start_at = job.get("startAt")
                end_at = job.get("endAt")
                window_start = (
                    datetime.fromisoformat(str(start_at).replace("Z", "+00:00"))
                    if start_at
                    else now
                )
                window_end = (
                    datetime.fromisoformat(str(end_at).replace("Z", "+00:00"))
                    if end_at
                    else window_start + timedelta(hours=2)
                )

                self.db.add(
                    DispatchJob(
                        org_id=org_id,
                        job_number=str(job.get("jobNumber") or f"JB-{jobber_id}")[:20],
                        customer_id=customer.customer_id,
                        technician_id=technician.technician_id if technician else None,
                        job_status=status,
                        priority="P3",
                        issue_type=str(job.get("jobType") or "SERVICE"),
                        issue_description=job.get("instructions")
                        or job.get("title")
                        or "Imported from Jobber",
                        scheduled_window_start=window_start,
                        scheduled_window_end=window_end,
                        external_job_id=external_job_id,
                        created_by="JOBBER_SYNC",
                    )
                )
                synced += 1

            page_info = jobs_block.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        await self.db.flush()
        return synced

    async def create_job_in_jobber(
        self,
        org_id: uuid.UUID,
        dispatch_job: DispatchJob,
        customer: Customer,
        technician: Technician,
    ) -> str | None:
        if not await self.has_active_connection(org_id):
            return None

        client_id = _parse_jobber_external_id(customer.external_id, "jobber")
        if not client_id:
            logger.warning(
                "Skipping Jobber job create for %s — customer has no Jobber external_id",
                dispatch_job.job_number,
            )
            return None

        job_input: dict[str, Any] = {
            "clientId": client_id,
            "title": f"{dispatch_job.issue_type} — {customer.full_name}",
            "instructions": dispatch_job.issue_description or "",
        }
        if dispatch_job.scheduled_window_start:
            job_input["startAt"] = dispatch_job.scheduled_window_start.isoformat()
        if dispatch_job.scheduled_window_end:
            job_input["endAt"] = dispatch_job.scheduled_window_end.isoformat()

        jobber_user_id = _parse_jobber_external_id(technician.external_id, "jobber")
        if not jobber_user_id:
            tech_meta = technician.metadata_ or {}
            jobber_user_id = tech_meta.get("jobber_user_id")
        if jobber_user_id:
            job_input["assignedTo"] = [str(jobber_user_id)]
        else:
            logger.info(
                "Creating Jobber job %s without technician assignment — "
                "technician has no Jobber external_id",
                dispatch_job.job_number,
            )

        try:
            payload = await self.graphql_query(
                org_id,
                CREATE_JOB_MUTATION,
                {"input": job_input},
            )
            result = (payload.get("data") or {}).get("jobCreate") or {}
            errors = result.get("userErrors") or []
            if errors:
                logger.error("Jobber jobCreate userErrors: %s", errors)
                return None
            job = result.get("job") or {}
            jobber_job_id = job.get("id")
            if not jobber_job_id:
                return None
            dispatch_job.external_job_id = f"jobber:{jobber_job_id}"
            await self.db.flush()
            return str(jobber_job_id)
        except Exception as exc:
            logger.exception(
                "Jobber job creation failed for %s: %s",
                dispatch_job.job_number,
                exc,
            )
            return None
