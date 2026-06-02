from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ServiceCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_id: str
    org_id: str
    service_code: str
    service_name: str
    category: str
    description: Optional[str] = None
    base_price_usd: Optional[Decimal] = None
    price_max_usd: Optional[Decimal] = None
    price_notes: Optional[str] = None
    duration_minutes_min: Optional[int] = None
    duration_minutes_max: Optional[int] = None
    is_active: bool
    requires_equipment_type: Optional[str] = None
    emergency_surcharge_pct: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime


class ServiceCatalogCreate(BaseModel):
    service_code: str = Field(max_length=100)
    service_name: str = Field(max_length=255)
    category: str = Field(max_length=100)
    description: Optional[str] = None
    base_price_usd: Optional[Decimal] = None
    price_max_usd: Optional[Decimal] = None
    price_notes: Optional[str] = Field(default=None, max_length=500)
    duration_minutes_min: Optional[int] = None
    duration_minutes_max: Optional[int] = None
    is_active: bool = True
    requires_equipment_type: Optional[str] = Field(default=None, max_length=100)
    emergency_surcharge_pct: Optional[Decimal] = None


class ServiceCatalogUpdate(BaseModel):
    service_code: Optional[str] = Field(default=None, max_length=100)
    service_name: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    base_price_usd: Optional[Decimal] = None
    price_max_usd: Optional[Decimal] = None
    price_notes: Optional[str] = Field(default=None, max_length=500)
    duration_minutes_min: Optional[int] = None
    duration_minutes_max: Optional[int] = None
    is_active: Optional[bool] = None
    requires_equipment_type: Optional[str] = Field(default=None, max_length=100)
    emergency_surcharge_pct: Optional[Decimal] = None


class ServiceCatalogListResponse(BaseModel):
    org_id: str
    total: int
    items: list[ServiceCatalogItem]
