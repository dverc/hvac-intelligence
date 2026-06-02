#!/usr/bin/env python3
"""Seed sample HVAC services for the seed organization (idempotent)."""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from app.core.constants import SEED_ORG_ID  # noqa: E402
from app.core.database import get_session_factory  # noqa: E402
from app.models.service_catalog import ServiceCatalog  # noqa: E402

SERVICES = [
    {
        "service_code": "AC_DIAGNOSTIC",
        "service_name": "AC Diagnostic",
        "category": "diagnostic",
        "description": "Full system diagnostic including refrigerant check, airflow test, and electrical inspection.",
        "base_price_usd": Decimal("89"),
        "price_max_usd": Decimal("129"),
        "duration_minutes_min": 45,
        "duration_minutes_max": 60,
    },
    {
        "service_code": "AC_REFRIGERANT_RECHARGE",
        "service_name": "AC Refrigerant Recharge",
        "category": "repair",
        "description": "Leak check, vacuum, and refrigerant recharge for central AC or heat pump.",
        "base_price_usd": Decimal("150"),
        "price_max_usd": Decimal("300"),
        "price_notes": "Parts additional",
        "duration_minutes_min": 60,
        "duration_minutes_max": 90,
    },
    {
        "service_code": "AC_CAPACITOR_REPLACE",
        "service_name": "AC Capacitor Replacement",
        "category": "repair",
        "description": "Replace failed run or start capacitor on outdoor condenser unit.",
        "base_price_usd": Decimal("120"),
        "price_max_usd": Decimal("200"),
        "duration_minutes_min": 30,
        "duration_minutes_max": 45,
        "requires_equipment_type": "AC_UNIT",
    },
    {
        "service_code": "FURNACE_DIAGNOSTIC",
        "service_name": "Furnace Diagnostic",
        "category": "diagnostic",
        "description": "Combustion analysis, heat exchanger inspection, and safety control check.",
        "base_price_usd": Decimal("89"),
        "price_max_usd": Decimal("129"),
        "duration_minutes_min": 45,
        "duration_minutes_max": 60,
    },
    {
        "service_code": "FURNACE_IGNITER_REPLACE",
        "service_name": "Furnace Igniter Replacement",
        "category": "repair",
        "description": "Replace hot surface igniter or spark igniter on gas furnace.",
        "base_price_usd": Decimal("150"),
        "price_max_usd": Decimal("250"),
        "duration_minutes_min": 45,
        "duration_minutes_max": 60,
        "requires_equipment_type": "FURNACE",
    },
    {
        "service_code": "HVAC_TUNE_UP",
        "service_name": "HVAC Tune-Up",
        "category": "maintenance",
        "description": "Annual maintenance: filter change, coil cleaning, thermostat calibration, safety check.",
        "base_price_usd": Decimal("129"),
        "price_max_usd": Decimal("129"),
        "price_notes": "Annual maintenance plan available",
        "duration_minutes_min": 60,
        "duration_minutes_max": 90,
    },
    {
        "service_code": "EMERGENCY_CALL",
        "service_name": "Emergency Service Call",
        "category": "emergency",
        "description": "After-hours or same-day emergency dispatch for no-heat or no-cool situations.",
        "base_price_usd": Decimal("199"),
        "price_notes": "199 surcharge plus standard service fee; 0-24h response",
        "duration_minutes_min": 0,
        "duration_minutes_max": 1440,
        "emergency_surcharge_pct": Decimal("25"),
    },
    {
        "service_code": "HVAC_INSTALL_QUOTE",
        "service_name": "HVAC Installation Quote",
        "category": "installation",
        "description": "On-site assessment and written estimate for new system installation or replacement.",
        "base_price_usd": Decimal("0"),
        "price_max_usd": Decimal("0"),
        "price_notes": "Free estimate",
        "duration_minutes_min": 60,
        "duration_minutes_max": 60,
    },
]


async def main() -> None:
    inserted = 0
    skipped = 0
    async with get_session_factory()() as session:
        for spec in SERVICES:
            existing = (
                await session.execute(
                    select(ServiceCatalog).where(
                        ServiceCatalog.org_id == SEED_ORG_ID,
                        ServiceCatalog.service_code == spec["service_code"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            session.add(ServiceCatalog(org_id=SEED_ORG_ID, **spec))
            inserted += 1
        await session.commit()
    print(f"Seed complete: {inserted} inserted, {skipped} skipped (already exist).")


if __name__ == "__main__":
    asyncio.run(main())
