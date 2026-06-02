from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import scoped
from app.models.service_catalog import ServiceCatalog
from app.schemas.service_catalog import (
    ServiceCatalogCreate,
    ServiceCatalogItem,
    ServiceCatalogUpdate,
)


def _to_item(row: ServiceCatalog) -> ServiceCatalogItem:
    return ServiceCatalogItem(
        service_id=str(row.service_id),
        org_id=str(row.org_id),
        service_code=row.service_code,
        service_name=row.service_name,
        category=row.category,
        description=row.description,
        base_price_usd=row.base_price_usd,
        price_max_usd=row.price_max_usd,
        price_notes=row.price_notes,
        duration_minutes_min=row.duration_minutes_min,
        duration_minutes_max=row.duration_minutes_max,
        is_active=row.is_active,
        requires_equipment_type=row.requires_equipment_type,
        emergency_surcharge_pct=row.emergency_surcharge_pct,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def format_price_range(item: ServiceCatalogItem | ServiceCatalog) -> str:
    base = item.base_price_usd
    max_price = item.price_max_usd
    if base is not None and max_price is not None:
        if base == max_price:
            return f"${base:.0f}"
        return f"${base:.0f} - ${max_price:.0f}"
    if base is not None:
        return f"${base:.0f}"
    if max_price is not None:
        return f"Up to ${max_price:.0f}"
    return "Contact for quote"


def format_duration(item: ServiceCatalogItem | ServiceCatalog) -> str:
    min_d = item.duration_minutes_min
    max_d = item.duration_minutes_max
    if min_d is not None and max_d is not None:
        if min_d == max_d:
            return f"{min_d} minutes"
        return f"{min_d}-{max_d} minutes"
    if min_d is not None:
        return f"{min_d}+ minutes"
    if max_d is not None:
        return f"Up to {max_d} minutes"
    return "Varies"


def build_service_rag_text(row: ServiceCatalog) -> str:
    price = format_price_range(row)
    duration = format_duration(row)
    parts = [
        f"Service: {row.service_name}.",
        f"Category: {row.category}.",
        f"Price: {price}.",
        f"Duration: {duration}.",
    ]
    if row.description:
        parts.append(row.description)
    if row.price_notes:
        parts.append(row.price_notes)
    return " ".join(parts)


class ServiceCatalogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def lookup(
        self,
        org_id: uuid.UUID,
        query: Optional[str] = None,
        category: Optional[str] = None,
        service_code: Optional[str] = None,
    ) -> list[ServiceCatalogItem]:
        stmt = select(ServiceCatalog).where(
            ServiceCatalog.org_id == org_id,
            ServiceCatalog.is_active.is_(True),
        )
        if service_code:
            stmt = stmt.where(ServiceCatalog.service_code == service_code.upper())
        if category:
            stmt = stmt.where(ServiceCatalog.category == category.lower())
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    ServiceCatalog.service_name.ilike(pattern),
                    ServiceCatalog.description.ilike(pattern),
                )
            )
        stmt = stmt.order_by(ServiceCatalog.service_name).limit(5)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_to_item(row) for row in rows]

    async def list_all(self, org_id: uuid.UUID) -> list[ServiceCatalogItem]:
        stmt = scoped(
            select(ServiceCatalog).order_by(ServiceCatalog.service_name),
            ServiceCatalog,
            org_id,
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_to_item(row) for row in rows]

    async def get_by_id(
        self, org_id: uuid.UUID, service_id: uuid.UUID
    ) -> ServiceCatalog | None:
        stmt = select(ServiceCatalog).where(
            ServiceCatalog.service_id == service_id,
            ServiceCatalog.org_id == org_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(
        self, org_id: uuid.UUID, data: ServiceCatalogCreate
    ) -> ServiceCatalogItem:
        row = ServiceCatalog(
            org_id=org_id,
            service_code=data.service_code.upper(),
            service_name=data.service_name,
            category=data.category.lower(),
            description=data.description,
            base_price_usd=data.base_price_usd,
            price_max_usd=data.price_max_usd,
            price_notes=data.price_notes,
            duration_minutes_min=data.duration_minutes_min,
            duration_minutes_max=data.duration_minutes_max,
            is_active=data.is_active,
            requires_equipment_type=data.requires_equipment_type,
            emergency_surcharge_pct=data.emergency_surcharge_pct or Decimal("0"),
        )
        self.db.add(row)
        await self.db.flush()
        return _to_item(row)

    async def update(
        self,
        org_id: uuid.UUID,
        service_id: uuid.UUID,
        data: ServiceCatalogUpdate,
    ) -> ServiceCatalogItem | None:
        row = await self.get_by_id(org_id, service_id)
        if row is None:
            return None
        updates = data.model_dump(exclude_unset=True)
        if "service_code" in updates and updates["service_code"] is not None:
            updates["service_code"] = updates["service_code"].upper()
        if "category" in updates and updates["category"] is not None:
            updates["category"] = updates["category"].lower()
        for key, value in updates.items():
            setattr(row, key, value)
        await self.db.flush()
        await self.db.refresh(row)
        return _to_item(row)

    async def delete(self, org_id: uuid.UUID, service_id: uuid.UUID) -> bool:
        row = await self.get_by_id(org_id, service_id)
        if row is None:
            return False
        row.is_active = False
        await self.db.flush()
        return True
