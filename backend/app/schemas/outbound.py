from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CampaignType = Literal["REACTIVATION", "RETENTION", "REMINDER"]
CampaignStatus = Literal["DRAFT", "ACTIVE", "PAUSED", "COMPLETED"]
DisclosureStyle = Literal["FRIENDLY", "FORMAL"]
ConsentType = Literal["OUTBOUND_CALL", "SMS", "RECORDING"]
ConsentMethod = Literal["VERBAL_INBOUND", "SMS_OPTIN", "WRITTEN_FORM", "VERBAL"]


class CampaignCreate(BaseModel):
    campaign_name: str = Field(min_length=1, max_length=255)
    campaign_type: CampaignType
    churn_score_threshold: float = Field(ge=0.60, le=0.90, default=0.75)
    max_attempts: int = Field(ge=1, le=3, default=2)
    calling_hours_start: int = Field(ge=8, le=20, default=9)
    calling_hours_end: int = Field(ge=9, le=21, default=18)
    disclosure_style: DisclosureStyle = "FRIENDLY"


class CampaignStatusUpdate(BaseModel):
    status: CampaignStatus


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campaign_id: uuid.UUID
    org_id: uuid.UUID
    campaign_name: str
    campaign_type: str
    status: str
    churn_score_threshold: Decimal
    max_attempts: int
    calling_hours_start: int
    calling_hours_end: int
    disclosure_style: str
    total_customers_targeted: int
    total_calls_made: int
    total_consented: int
    total_booked: int
    created_at: datetime
    updated_at: datetime
    conversion_rate: float = 0.0


class CampaignCustomerOut(BaseModel):
    customer_id: str
    full_name: str
    phone_primary: str
    churn_probability: float | None
    eligible: bool
    reason: str
    checks: dict


class EligibilityPreview(BaseModel):
    eligible_count: int
    churn_score_threshold: float


class ConsentCreate(BaseModel):
    consent_type: ConsentType
    consent_method: ConsentMethod
    consent_text: str = Field(min_length=1)
    call_id: Optional[str] = None


class ConsentStatusOut(BaseModel):
    customer_id: str
    dnc: bool
    active_consents: list[dict]


class EligibilityOut(BaseModel):
    eligible: bool
    reason: str
    checks: dict


class BlockedAttemptOut(BaseModel):
    attempt_id: str
    customer_id: str
    customer_name: str
    block_reason: str
    notes: str | None
    timestamp: str


class CampaignExecuteResponse(BaseModel):
    status: str
    message: str
    campaign_id: str
