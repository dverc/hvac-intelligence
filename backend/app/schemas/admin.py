from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class OrgSettingsOut(BaseModel):
    setting_id: uuid.UUID
    org_id: uuid.UUID
    display_name: str | None = None
    phone_display: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    agent_greeting: str | None = None
    agent_name: str = "AI Assistant"
    business_hours_start: int = 8
    business_hours_end: int = 18
    timezone: str = "America/Los_Angeles"
    vapi_assistant_id: str | None = None
    vapi_phone_number_id: str | None = None
    vapi_phone_number: str | None = None
    outbound_enabled: bool = False
    outbound_disclosure_style: str = "FRIENDLY"
    max_outbound_attempts: int = 2
    onboarding_completed: bool = False
    onboarding_step: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminOrganizationListItem(BaseModel):
    org_id: uuid.UUID
    org_name: str
    slug: str
    industry: str
    plan_tier: str
    is_active: bool
    status: Literal["ACTIVE", "TRIAL", "INACTIVE"]
    user_count: int
    technician_count: int
    onboarding_completed: bool
    onboarding_step: int
    display_name: str | None = None
    created_at: datetime


class AdminOrganizationCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    admin_email: EmailStr
    admin_first_name: str = Field(default="", max_length=100)
    admin_last_name: str = Field(default="", max_length=100)
    industry: str = "hvac"
    plan_tier: str = "starter"


class AdminOrganizationCreateResponse(BaseModel):
    org_id: uuid.UUID
    org_name: str
    slug: str
    settings: OrgSettingsOut
    admin_user_id: str | None = None
    temporary_password: str | None = None


class AdminOrganizationDetail(BaseModel):
    org_id: uuid.UUID
    org_name: str
    slug: str
    industry: str
    business_phone: str | None = None
    plan_tier: str
    is_active: bool
    status: Literal["ACTIVE", "TRIAL", "INACTIVE"]
    user_count: int
    technician_count: int
    settings: OrgSettingsOut | None = None
    created_at: datetime
    updated_at: datetime


class AdminOrganizationUpdate(BaseModel):
    org_name: str | None = None
    industry: str | None = None
    plan_tier: str | None = None
    is_active: bool | None = None
    business_phone: str | None = None
    display_name: str | None = None
    phone_display: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    agent_greeting: str | None = None
    agent_name: str | None = None
    business_hours_start: int | None = None
    business_hours_end: int | None = None
    timezone: str | None = None
    vapi_assistant_id: str | None = None
    vapi_phone_number_id: str | None = None
    vapi_phone_number: str | None = None
    outbound_enabled: bool | None = None
    outbound_disclosure_style: str | None = None
    max_outbound_attempts: int | None = None
    onboarding_step: int | None = None


class AdminUserCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    role: Literal["admin", "dispatcher", "read_only"] = "admin"


class AdminUserCreateResponse(BaseModel):
    user_id: str
    email: str
    role: str
    org_id: str
    temporary_password: str


class AdminUserOut(BaseModel):
    user_id: str
    email: str
    role: str
    org_id: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AdminTechnicianCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    email: str | None = None
    specialty: str = "HVAC"


class AdminTechnicianOut(BaseModel):
    technician_id: uuid.UUID
    full_name: str
    phone: str | None = None
    email: str | None = None
    specialty: str | None = None
    employment_status: str


class OnboardingProgressOut(BaseModel):
    org_id: uuid.UUID
    onboarding_completed: bool
    onboarding_step: int
    display_name: str | None = None


class OnboardingProgressUpdate(BaseModel):
    onboarding_step: int | None = None
    onboarding_completed: bool | None = None


class ProvisionResponse(BaseModel):
    org_id: uuid.UUID
    settings: OrgSettingsOut
    example_customer_created: bool
