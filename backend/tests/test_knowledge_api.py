import io
import uuid
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import SEED_ORG_ID, SEED_ORG_ID_STR
from app.schemas.service_catalog import ServiceCatalogCreate


@pytest.mark.asyncio
async def test_upload_and_list_document(api_client, db_session):
    org_id = SEED_ORG_ID_STR
    content = b"# Test FAQ\n\nOur diagnostic fee starts at $89."
    files = {"file": ("test-faq.md", io.BytesIO(content), "text/markdown")}

    upload = await api_client.post(
        f"/api/v1/knowledge/{org_id}/documents",
        files=files,
        data={"namespace": "faq_general", "document_id": "test-upload-doc"},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["document_id"] == "test-upload-doc"
    assert body["chunks_indexed"] >= 1

    listing = await api_client.get(f"/api/v1/knowledge/{org_id}/documents")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert any(item["document_id"] == "test-upload-doc" for item in items)


@pytest.mark.asyncio
async def test_delete_document_soft(api_client, db_session):
    org_id = SEED_ORG_ID_STR
    content = b"Temporary document for delete test."
    files = {"file": ("delete-me.txt", io.BytesIO(content), "text/plain")}

    await api_client.post(
        f"/api/v1/knowledge/{org_id}/documents",
        files=files,
        data={"document_id": "delete-me-doc"},
    )

    deleted = await api_client.delete(
        f"/api/v1/knowledge/{org_id}/documents/delete-me-doc"
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    listing = await api_client.get(f"/api/v1/knowledge/{org_id}/documents")
    active_ids = [item["document_id"] for item in listing.json()["items"]]
    assert "delete-me-doc" not in active_ids


@pytest.mark.asyncio
async def test_create_service_catalog_via_knowledge_api(api_client, db_session):
    org_id = SEED_ORG_ID_STR
    response = await api_client.post(
        f"/api/v1/knowledge/{org_id}/service-catalog",
        json={
            "service_code": "API_CREATE_TEST",
            "service_name": "API Create Test",
            "category": "inspection",
            "base_price_usd": "50.00",
            "price_max_usd": "75.00",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["service_code"] == "API_CREATE_TEST"


@pytest.mark.asyncio
async def test_patch_service_catalog_updates_price(api_client, db_session):
    from app.services.service_catalog_service import ServiceCatalogService

    org_id = SEED_ORG_ID
    catalog = ServiceCatalogService(db_session)
    created = await catalog.create(
        org_id,
        ServiceCatalogCreate(
            service_code="PATCH_VIA_API",
            service_name="Patch Via API",
            category="repair",
            base_price_usd=Decimal("100"),
        ),
    )
    await db_session.commit()

    response = await api_client.patch(
        f"/api/v1/knowledge/{SEED_ORG_ID_STR}/service-catalog/{created.service_id}",
        json={"base_price_usd": "199.00"},
    )
    assert response.status_code == 200
    assert response.json()["base_price_usd"] in ("199.00", 199.0, "199")
