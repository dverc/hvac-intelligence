from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Industry = Literal[
    "hvac",
    "plumbing",
    "electrical",
    "isp",
    "appliance_repair",
    "locksmith",
    "pest_control",
    "other",
]


class BusinessHoursDay(BaseModel):
    open: str
    close: str


class OnboardingProvisionRequest(BaseModel):
    business_name: Optional[str] = None
    trade_type: Industry = "hvac"
    phone_number: Optional[str] = None
    agent_name: str = Field(min_length=1, default="Alex")
    timezone: str = Field(min_length=1, default="America/Los_Angeles")
    business_hours: dict[str, BusinessHoursDay | None] = Field(default_factory=dict)
    notification_email: str = Field(min_length=1, default="")
    service_zip_codes: Optional[list[str]] = None


class OnboardingProvisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_id: uuid.UUID
    org_name: str
    slug: str
    agent_name: str
    dashboard_api_key: str
