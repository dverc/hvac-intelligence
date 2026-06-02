from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.equipment import Equipment
from app.schemas.tools import CreateEquipmentArgs

_DB_EQUIPMENT_TYPES = {
    "AC_UNIT",
    "FURNACE",
    "HEAT_PUMP",
    "AIR_HANDLER",
    "MINI_SPLIT",
    "OTHER",
}


def _normalize_equipment_type(equipment_type: str) -> tuple[str, dict[str, Any]]:
    """Map voice-tool types to DB check-constraint values."""
    if equipment_type in _DB_EQUIPMENT_TYPES:
        return equipment_type, {}
    return "OTHER", {"original_equipment_type": equipment_type}


class EquipmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_equipment(self, args: CreateEquipmentArgs) -> dict[str, Any]:
        customer = await self.db.get(Customer, uuid.UUID(args.customer_id))
        if customer is None:
            return {
                "success": False,
                "error": f"Customer {args.customer_id} not found",
            }

        db_type, extra_metadata = _normalize_equipment_type(args.equipment_type)
        install_date = None
        if args.install_year is not None:
            install_date = date(args.install_year, 1, 1)

        metadata = dict(extra_metadata)
        if args.install_year is not None and args.equipment_type not in _DB_EQUIPMENT_TYPES:
            metadata["install_year"] = args.install_year

        equipment = Equipment(
            customer_id=customer.customer_id,
            make=args.make or "Unknown",
            model=args.model or "Unknown",
            serial_number=args.serial_number,
            equipment_type=db_type,
            install_date=install_date,
            known_issues=args.known_issues or [],
            metadata_=metadata,
        )
        self.db.add(equipment)
        await self.db.flush()

        display_make = args.make or "Unknown"
        display_model = args.model or "Unknown"
        return {
            "success": True,
            "equipment_id": str(equipment.equipment_id),
            "customer_id": str(customer.customer_id),
            "equipment_type": args.equipment_type,
            "make": display_make,
            "model": display_model,
            "summary": (
                f"{display_make} {display_model} ({args.equipment_type}) "
                f"registered for {customer.full_name}."
            ),
        }
