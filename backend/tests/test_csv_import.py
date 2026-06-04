from __future__ import annotations

import pytest

from app.core.constants import SEED_ORG_ID
from app.services.csv_import_service import CsvImportService
from app.services.customer_service import normalize_phone


def _customer_csv(rows: str) -> bytes:
    header = "full_name,phone,email,address,city,state,zip,contract_type,notes\n"
    return (header + rows).encode("utf-8")


def _equipment_csv(rows: str) -> bytes:
    header = (
        "customer_phone,equipment_type,make,model,install_year,serial_number,known_issues\n"
    )
    return (header + rows).encode("utf-8")


@pytest.mark.asyncio
async def test_valid_customer_csv_imports_all_rows(db_session):
    svc = CsvImportService(db_session, SEED_ORG_ID)
    content = _customer_csv(
        "Alice A,+19491110001,alice@a.com,1 St,Irvine,CA,92618,RESIDENTIAL_OTC,\n"
        "Bob B,9492220002,bob@b.com,2 St,Irvine,CA,92618,ANNUAL_MAINTENANCE,\n"
    )
    result = await svc.import_customers(content, "customers.csv", dry_run=False)
    assert result.imported == 2
    assert result.errors == []


@pytest.mark.asyncio
async def test_customer_csv_duplicate_phone_skips(db_session, seeded_customer):
    phone = seeded_customer["phone"]
    svc = CsvImportService(db_session, SEED_ORG_ID)
    content = _customer_csv(f"Dup User,{phone},dup@x.com,,,,,,\n")
    result = await svc.import_customers(content, "customers.csv")
    assert result.imported == 0
    assert result.skipped == 1
    assert any("duplicate phone" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_customer_csv_missing_required_fields_returns_error(db_session):
    svc = CsvImportService(db_session, SEED_ORG_ID)
    content = _customer_csv(",+19498887777,,,,,,,\n")
    result = await svc.import_customers(content, "customers.csv")
    assert result.imported == 0
    assert result.errors


@pytest.mark.asyncio
async def test_dry_run_does_not_write_customers(db_session):
    svc = CsvImportService(db_session, SEED_ORG_ID)
    content = _customer_csv("Dry Run,+19493339999,dry@x.com,,,,,,\n")
    result = await svc.import_customers(content, "customers.csv", dry_run=True)
    assert result.imported == 1
    assert result.dry_run is True
    found = await svc.customers.lookup_by_phone("+19493339999", SEED_ORG_ID)
    assert found is None


@pytest.mark.asyncio
async def test_equipment_csv_links_by_phone(db_session, seeded_customer):
    phone = seeded_customer["phone"]
    svc = CsvImportService(db_session, SEED_ORG_ID)
    content = _equipment_csv(
        f"{phone},AC_UNIT,Carrier,ModelX,2019,SN1,noise|leak\n"
    )
    result = await svc.import_equipment(content, "equipment.csv")
    assert result.imported == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_equipment_csv_skips_when_customer_missing(db_session):
    svc = CsvImportService(db_session, SEED_ORG_ID)
    content = _equipment_csv("+19999999999,AC_UNIT,Carrier,ModelX,2019,SN1,\n")
    result = await svc.import_equipment(content, "equipment.csv")
    assert result.imported == 0
    assert result.skipped == 1


@pytest.mark.asyncio
async def test_generate_customer_template_returns_csv_bytes(db_session):
    svc = CsvImportService(db_session, SEED_ORG_ID)
    data = svc.generate_customer_template()
    text = data.decode("utf-8")
    assert "full_name" in text
    assert "Jane Doe" in text


def test_phone_normalization():
    assert normalize_phone("9493313190") == "+19493313190"
