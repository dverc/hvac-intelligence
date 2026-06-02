import uuid
from decimal import Decimal

import pytest

from app.core.constants import SEED_ORG_ID
from app.schemas.service_catalog import ServiceCatalogCreate, ServiceCatalogUpdate
from app.services.service_catalog_service import ServiceCatalogService


@pytest.fixture
def catalog_service(db_session):
    return ServiceCatalogService(db_session)


@pytest.mark.asyncio
async def test_lookup_by_service_code_exact_match(catalog_service, db_session):
    await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="TEST_LOOKUP",
            service_name="Test Lookup Service",
            category="diagnostic",
            base_price_usd=Decimal("99"),
            price_max_usd=Decimal("149"),
        ),
    )
    await db_session.commit()

    results = await catalog_service.lookup(
        SEED_ORG_ID, service_code="TEST_LOOKUP"
    )
    assert len(results) == 1
    assert results[0].service_code == "TEST_LOOKUP"


@pytest.mark.asyncio
async def test_lookup_by_category(catalog_service, db_session):
    await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="CAT_A",
            service_name="Category A Service",
            category="repair",
        ),
    )
    await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="CAT_B",
            service_name="Category B Service",
            category="diagnostic",
        ),
    )
    await db_session.commit()

    results = await catalog_service.lookup(SEED_ORG_ID, category="repair")
    assert len(results) >= 1
    assert all(item.category == "repair" for item in results)


@pytest.mark.asyncio
async def test_lookup_by_query_ilike(catalog_service, db_session):
    await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="UNIQUE_QUERY_XYZ",
            service_name="Super Special Capacitor Fix",
            category="repair",
            description="Replaces capacitors on outdoor units",
        ),
    )
    await db_session.commit()

    results = await catalog_service.lookup(SEED_ORG_ID, query="capacitor")
    codes = [item.service_code for item in results]
    assert "UNIQUE_QUERY_XYZ" in codes


@pytest.mark.asyncio
async def test_create_appears_in_list_all(catalog_service, db_session):
    created = await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="LIST_TEST",
            service_name="List Test Service",
            category="maintenance",
        ),
    )
    await db_session.commit()

    items = await catalog_service.list_all(SEED_ORG_ID)
    assert any(item.service_id == created.service_id for item in items)


@pytest.mark.asyncio
async def test_update_changes_price(catalog_service, db_session):
    created = await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="PRICE_UPDATE",
            service_name="Price Update Service",
            category="repair",
            base_price_usd=Decimal("100"),
        ),
    )
    await db_session.commit()

    updated = await catalog_service.update(
        SEED_ORG_ID,
        uuid.UUID(created.service_id),
        ServiceCatalogUpdate(base_price_usd=Decimal("175")),
    )
    assert updated is not None
    assert updated.base_price_usd == Decimal("175")


@pytest.mark.asyncio
async def test_delete_soft_excludes_from_lookup(catalog_service, db_session):
    created = await catalog_service.create(
        SEED_ORG_ID,
        ServiceCatalogCreate(
            service_code="SOFT_DELETE",
            service_name="Soft Delete Service",
            category="repair",
        ),
    )
    await db_session.commit()

    ok = await catalog_service.delete(SEED_ORG_ID, uuid.UUID(created.service_id))
    assert ok is True
    await db_session.commit()

    results = await catalog_service.lookup(
        SEED_ORG_ID, service_code="SOFT_DELETE"
    )
    assert results == []
