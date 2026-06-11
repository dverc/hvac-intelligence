from __future__ import annotations

import uuid
from datetime import datetime
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
PlanTier = Literal["starter", "professional", "enterprise"]


class OrganizationSettings(BaseModel):
    """Validated tenant configuration blob (stored in organizations.settings)."""

    model_config = ConfigDict(extra="allow")  # forward-compatible

    pinecone_namespace: str = "faq_general"
    issue_taxonomy: list[str] = Field(default_factory=list)
    customer_segments: list[str] = Field(default_factory=lambda: ["residential"])
    timezone: str = "America/Los_Angeles"
    business_hours: dict | None = None
    enabled_tools: list[str] | None = None  # None = all tools enabled
    system_prompt_override: str | None = None
    first_message: str | None = None
    # Outbound calling (client-configurable; legal disclosures are always enforced)
    outbound_enabled: bool = False
    outbound_display_name: str | None = None
    outbound_disclosure_style: str = "FRIENDLY"
    outbound_churn_threshold: float = 0.75
    outbound_max_attempts: int = 2
    outbound_calling_hours_start: int = 9
    outbound_calling_hours_end: int = 18
    outbound_campaign_type: str = "REACTIVATION"


class OrganizationCreate(BaseModel):
    org_name: str
    slug: str = Field(min_length=1, max_length=100)
    industry: Industry
    business_phone: Optional[str] = None
    vapi_assistant_id: Optional[str] = None
    vapi_phone_number: Optional[str] = None
    agent_name: Optional[str] = None
    vapi_phone_number_id: Optional[str] = None
    plan_tier: PlanTier = "starter"
    is_active: bool = True
    settings: OrganizationSettings = Field(default_factory=OrganizationSettings)


class OrganizationUpdate(BaseModel):
    """Partial update. `settings` is DEEP-MERGED into existing settings."""

    model_config = ConfigDict(extra="forbid")

    org_name: Optional[str] = None
    slug: Optional[str] = Field(default=None, min_length=1, max_length=100)
    industry: Optional[Industry] = None
    business_phone: Optional[str] = None
    vapi_assistant_id: Optional[str] = None
    vapi_phone_number: Optional[str] = None
    agent_name: Optional[str] = None
    vapi_phone_number_id: Optional[str] = None
    plan_tier: Optional[PlanTier] = None
    is_active: Optional[bool] = None
    settings: Optional[dict] = None  # partial settings blob, deep-merged


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_id: uuid.UUID
    org_name: str
    slug: str
    industry: str
    business_phone: Optional[str] = None
    vapi_assistant_id: Optional[str] = None
    vapi_phone_number: Optional[str] = None
    agent_name: Optional[str] = None
    vapi_phone_number_id: Optional[str] = None
    plan_tier: str
    is_active: bool
    settings: dict
    created_at: datetime
    updated_at: datetime


class OrganizationListOut(OrganizationOut):
    customer_count: int = 0
