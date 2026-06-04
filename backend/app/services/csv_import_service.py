from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.equipment import Equipment
from app.schemas.imports import CsvImportResult
from app.schemas.tools import CreateCustomerArgs
from app.services.customer_service import CustomerService, normalize_phone
from app.services.equipment_service import _normalize_equipment_type

_CUSTOMER_HEADER_ALIASES: dict[str, list[str]] = {
    "full_name": ["full_name", "name", "customer_name"],
    "phone": ["phone", "phone_number", "mobile", "phone_primary"],
    "email": ["email", "email_address"],
    "address": ["address", "street", "address_line1"],
    "city": ["city"],
    "state": ["state", "province"],
    "zip": ["zip", "postal_code", "postcode"],
    "contract_type": ["contract_type", "contract"],
    "notes": ["notes", "comment", "comments"],
}

_EQUIPMENT_HEADER_ALIASES: dict[str, list[str]] = {
    "customer_phone": ["customer_phone", "phone", "phone_number"],
    "customer_email": ["customer_email", "email"],
    "customer_id": ["customer_id", "customer_uuid"],
    "equipment_type": ["equipment_type", "type"],
    "make": ["make", "brand", "manufacturer"],
    "model": ["model", "model_number"],
    "install_year": ["install_year", "year_installed", "year"],
    "serial_number": ["serial_number", "serial"],
    "known_issues": ["known_issues", "issues"],
}

_VALID_CONTRACT_TYPES = frozenset(
    {"RESIDENTIAL_OTC", "ANNUAL_MAINTENANCE", "COMMERCIAL_SLA"}
)


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _map_headers(fieldnames: list[str] | None, aliases: dict[str, list[str]]) -> dict[str, str]:
    if not fieldnames:
        return {}
    normalized = {_normalize_header(h): h for h in fieldnames if h}
    mapping: dict[str, str] = {}
    for canonical, options in aliases.items():
        for option in options:
            key = _normalize_header(option)
            if key in normalized:
                mapping[canonical] = normalized[key]
                break
    return mapping


def _row_value(row: dict[str, str], mapping: dict[str, str], field: str) -> str:
    header = mapping.get(field)
    if not header:
        return ""
    return (row.get(header) or "").strip()


def _parse_csv(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], []
    rows = [{k: (v or "").strip() for k, v in row.items()} for row in reader]
    return rows, list(reader.fieldnames)


class CsvImportService:
    def __init__(self, db: AsyncSession, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id
        self.customers = CustomerService(db)

    async def import_customers(
        self,
        file_content: bytes,
        filename: str,
        dry_run: bool = False,
    ) -> CsvImportResult:
        del filename
        rows, fieldnames = _parse_csv(file_content)
        mapping = _map_headers(fieldnames, _CUSTOMER_HEADER_ALIASES)
        if "full_name" not in mapping:
            return CsvImportResult(
                total_rows=0,
                imported=0,
                skipped=0,
                errors=[{"row": 0, "message": "Missing required column: full_name (or name)"}],
                dry_run=dry_run,
            )

        imported = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []

        for index, row in enumerate(rows, start=2):
            if not any(row.values()):
                continue
            name = _row_value(row, mapping, "full_name")
            phone_raw = _row_value(row, mapping, "phone")
            email = _row_value(row, mapping, "email") or None
            if not name:
                errors.append({"row": index, "message": "full_name is required"})
                continue
            if not phone_raw and not email:
                errors.append(
                    {"row": index, "message": "phone or email is required"}
                )
                continue

            phone_normalized: str | None = None
            if phone_raw:
                try:
                    phone_normalized = normalize_phone(phone_raw)
                except Exception:
                    errors.append({"row": index, "message": f"Invalid phone: {phone_raw}"})
                    continue

            if phone_normalized:
                existing = await self.customers.lookup_by_phone(
                    phone_normalized, self.org_id
                )
                if existing:
                    skipped += 1
                    warnings.append(
                        f"Row {index}: skipped duplicate phone {phone_normalized}"
                    )
                    continue
            if email:
                existing_email = await self.customers.get_by_email(email, self.org_id)
                if existing_email:
                    skipped += 1
                    warnings.append(f"Row {index}: skipped duplicate email {email}")
                    continue

            contract_type = (
                _row_value(row, mapping, "contract_type").upper() or "RESIDENTIAL_OTC"
            )
            if contract_type not in _VALID_CONTRACT_TYPES:
                errors.append(
                    {
                        "row": index,
                        "message": f"Invalid contract_type: {contract_type}",
                    }
                )
                continue

            state = (_row_value(row, mapping, "state") or "CA").upper()[:2]
            if len(state) != 2:
                state = "CA"

            if not phone_normalized and email:
                phone_normalized = f"+1555{uuid.uuid4().int % 10000000:07d}"

            if dry_run:
                imported += 1
                continue

            args = CreateCustomerArgs(
                full_name=name,
                phone_primary=phone_normalized or f"+1555{uuid.uuid4().int % 10000000:07d}",
                email=email,
                service_address_line1=_row_value(row, mapping, "address") or "—",
                service_address_city=_row_value(row, mapping, "city") or "—",
                service_address_state=state,
                service_address_zip=_row_value(row, mapping, "zip") or "00000",
                contract_type=contract_type,  # type: ignore[arg-type]
                notes=_row_value(row, mapping, "notes") or None,
            )
            result = await self.customers.create_customer(args, self.org_id)
            if result.get("success"):
                imported += 1
            else:
                skipped += 1
                warnings.append(
                    f"Row {index}: {result.get('error', 'create_customer failed')}"
                )

        return CsvImportResult(
            total_rows=len(rows),
            imported=imported,
            skipped=skipped,
            errors=errors,
            dry_run=dry_run,
            warnings=warnings,
        )

    async def _resolve_customer(
        self,
        row: dict[str, str],
        mapping: dict[str, str],
        row_num: int,
    ) -> Customer | None:
        customer_id_raw = _row_value(row, mapping, "customer_id")
        if customer_id_raw:
            try:
                cid = uuid.UUID(customer_id_raw)
            except ValueError:
                return None
            return await self.customers.get_by_id(cid, self.org_id)

        phone_raw = _row_value(row, mapping, "customer_phone")
        if phone_raw:
            return await self.customers.lookup_by_phone(phone_raw, self.org_id)

        email = _row_value(row, mapping, "customer_email")
        if email:
            return await self.customers.get_by_email(email, self.org_id)
        return None

    async def import_equipment(
        self,
        file_content: bytes,
        filename: str,
        dry_run: bool = False,
    ) -> CsvImportResult:
        del filename
        rows, fieldnames = _parse_csv(file_content)
        mapping = _map_headers(fieldnames, _EQUIPMENT_HEADER_ALIASES)
        if not any(
            mapping.get(k)
            for k in ("customer_phone", "customer_email", "customer_id")
        ):
            return CsvImportResult(
                total_rows=0,
                imported=0,
                skipped=0,
                errors=[
                    {
                        "row": 0,
                        "message": "Need customer_phone, customer_email, or customer_id",
                    }
                ],
                dry_run=dry_run,
            )

        imported = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []

        for index, row in enumerate(rows, start=2):
            if not any(row.values()):
                continue
            customer = await self._resolve_customer(row, mapping, index)
            if customer is None:
                skipped += 1
                warnings.append(f"Row {index}: customer not found — skipped")
                continue

            eq_type_raw = (
                _row_value(row, mapping, "equipment_type").upper() or "OTHER"
            )
            db_type, extra_meta = _normalize_equipment_type(eq_type_raw)
            install_year_raw = _row_value(row, mapping, "install_year")
            install_date = None
            if install_year_raw.isdigit():
                install_date = date(int(install_year_raw), 1, 1)

            issues_raw = _row_value(row, mapping, "known_issues")
            known_issues = (
                [p.strip() for p in issues_raw.split("|") if p.strip()]
                if issues_raw
                else []
            )

            if dry_run:
                imported += 1
                continue

            equipment = Equipment(
                org_id=self.org_id,
                customer_id=customer.customer_id,
                make=_row_value(row, mapping, "make") or "Unknown",
                model=_row_value(row, mapping, "model") or "Unknown",
                serial_number=_row_value(row, mapping, "serial_number") or None,
                equipment_type=db_type,
                install_date=install_date,
                known_issues=known_issues,
                metadata_=extra_meta,
            )
            self.db.add(equipment)
            imported += 1

        if not dry_run and imported:
            await self.db.flush()

        return CsvImportResult(
            total_rows=len(rows),
            imported=imported,
            skipped=skipped,
            errors=errors,
            dry_run=dry_run,
            warnings=warnings,
        )

    def generate_customer_template(self) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "full_name",
                "phone",
                "email",
                "address",
                "city",
                "state",
                "zip",
                "contract_type",
                "notes",
            ]
        )
        writer.writerow(
            [
                "Jane Doe",
                "9493313190",
                "jane@example.com",
                "123 Main St",
                "Irvine",
                "CA",
                "92618",
                "RESIDENTIAL_OTC",
                "Example customer row",
            ]
        )
        return buffer.getvalue().encode("utf-8")

    def generate_equipment_template(self) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "customer_phone",
                "customer_email",
                "equipment_type",
                "make",
                "model",
                "install_year",
                "serial_number",
                "known_issues",
            ]
        )
        writer.writerow(
            [
                "+19493313190",
                "",
                "AC_UNIT",
                "Carrier",
                "Infinity 24",
                "2018",
                "SN-12345",
                "noisy compressor|weak airflow",
            ]
        )
        return buffer.getvalue().encode("utf-8")
