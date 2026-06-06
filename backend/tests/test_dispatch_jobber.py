from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

from app.core.constants import SEED_ORG_ID
from app.core.encryption import encrypt_token
from app.models.jobber_token import JobberToken
from app.services.dispatch_service import DispatchService


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_create_job_attempts_jobber_write(
    db_session, seeded_customer, encryption_key
):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("access") or "",
        refresh_token=encrypt_token("refresh") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    with patch(
        "app.services.jobber_service.JobberService.create_job_in_jobber",
        new_callable=AsyncMock,
        return_value="jobber-job-123",
    ) as mock_create:
        svc = DispatchService(db_session)
        result = await svc.create_job(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_NO_COOLING",
            priority="P2",
            preferred_window="monday morning",
            issue_description="Jobber integration test",
            org_id=SEED_ORG_ID,
        )

    assert result["success"] is True
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_job_succeeds_when_jobber_fails(
    db_session, seeded_customer, encryption_key
):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("access") or "",
        refresh_token=encrypt_token("refresh") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    with patch(
        "app.services.jobber_service.JobberService.create_job_in_jobber",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Jobber API down"),
    ):
        svc = DispatchService(db_session)
        result = await svc.create_job(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_NO_COOLING",
            priority="P3",
            preferred_window="monday afternoon",
            issue_description="Non-blocking Jobber failure",
            org_id=SEED_ORG_ID,
        )

    assert result["success"] is True
    assert result.get("job_number")
