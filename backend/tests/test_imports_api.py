from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import SEED_ORG_ID_STR


@pytest.mark.asyncio
async def test_import_customers_valid_csv(api_client):
    csv_body = (
        "full_name,phone,email\n"
        "API Import,+19497770001,apiimport@example.com\n"
    ).encode("utf-8")
    response = await api_client.post(
        f"/api/v1/imports/{SEED_ORG_ID_STR}/customers",
        files={"file": ("customers.csv", io.BytesIO(csv_body), "text/csv")},
        data={"dry_run": "false"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] >= 1


@pytest.mark.asyncio
async def test_import_customers_dry_run(api_client):
    csv_body = b"full_name,phone,email\nTest User,+19497770002,t2@example.com\n"
    response = await api_client.post(
        f"/api/v1/imports/{SEED_ORG_ID_STR}/customers",
        files={"file": ("customers.csv", io.BytesIO(csv_body), "text/csv")},
        data={"dry_run": "true"},
    )
    assert response.status_code == 200
    assert response.json()["dry_run"] is True


@pytest.mark.asyncio
async def test_download_customer_template(api_client):
    response = await api_client.get(
        f"/api/v1/imports/{SEED_ORG_ID_STR}/templates/customers"
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert b"full_name" in response.content


@pytest.mark.asyncio
async def test_drive_sync_returns_counts(api_client):
    with patch(
        "app.services.google_drive_service.GoogleDriveService.sync_folder_to_knowledge_base",
        new_callable=AsyncMock,
    ) as mock_sync:
        mock_sync.return_value = {"synced": 2, "skipped": 1, "errors": 0}
        response = await api_client.post(
            f"/api/v1/imports/{SEED_ORG_ID_STR}/drive/sync"
        )
    assert response.status_code == 200
    assert response.json()["synced"] == 2
