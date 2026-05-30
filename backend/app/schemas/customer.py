from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerAddressPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class CustomerUpdate(BaseModel):
    """Partial customer update — only set fields are applied."""

    model_config = ConfigDict(extra="forbid")

    external_id: Optional[str] = None
    full_name: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    email: Optional[str] = None
    account_status: Optional[
        Literal["ACTIVE", "SUSPENDED", "CHURNED", "PROSPECT"]
    ] = None
    customer_since: Optional[date] = None
    contract_type: Optional[
        Literal["ANNUAL_MAINTENANCE", "RESIDENTIAL_OTC", "COMMERCIAL_SLA"]
    ] = None
    contract_value_usd: Optional[float] = Field(default=None, ge=0)
    payment_method: Optional[str] = None
    preferred_tech_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    address: Optional[CustomerAddressPatch] = None
