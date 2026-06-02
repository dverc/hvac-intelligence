from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ChurnRiskContext(BaseModel):
    risk_tier: Optional[str] = None
    score: Optional[float] = None


class ScheduleDispatchArgs(BaseModel):
    customer_id: str
    issue_type: str
    priority: Literal["P1", "P2", "P3", "P4"]
    preferred_window: str
    issue_description: str
    equipment_id: Optional[str] = None
    access_instructions: Optional[str] = None
    churn_risk_context: Optional[ChurnRiskContext] = None


class QueryChurnScoreArgs(BaseModel):
    customer_id: str


class GetCustomerInfoArgs(BaseModel):
    lookup_method: Literal["phone", "customer_id", "email"]
    lookup_value: str


class GetEquipmentInfoArgs(BaseModel):
    customer_id: str
    equipment_id: Optional[str] = None


class RagKnowledgeQueryArgs(BaseModel):
    query: str
    equipment_model: Optional[str] = None
    namespace: Optional[
        Literal["faq_general", "equipment_manuals", "warranty_terms", "troubleshooting", "pricing"]
    ] = None
    top_k: int = Field(default=5, ge=1, le=10)


class CreateSupportTicketArgs(BaseModel):
    customer_id: str
    ticket_type: Literal[
        "BILLING_DISPUTE",
        "WARRANTY_CLAIM",
        "COMPLAINT_ESCALATION",
        "SAFETY_CONCERN",
        "REFUND_REQUEST",
        "MANAGER_CALLBACK",
        "UNRESOLVED_TECHNICAL",
    ]
    subject: str
    description: str
    priority: Literal["P1", "P2", "P3"]
    preferred_callback_time: Optional[str] = None


class ToolCallPayload(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CreateCustomerArgs(BaseModel):
    full_name: str
    phone_primary: str
    service_address_line1: str
    service_address_city: str
    service_address_state: str = Field(min_length=2, max_length=2)
    service_address_zip: str
    email: Optional[str] = None
    contract_type: Literal[
        "RESIDENTIAL_OTC", "ANNUAL_MAINTENANCE", "COMMERCIAL_SLA"
    ] = "RESIDENTIAL_OTC"
    notes: Optional[str] = None


class UpdateCustomerArgs(BaseModel):
    customer_id: str
    full_name: Optional[str] = None
    phone_primary: Optional[str] = None
    email: Optional[str] = None
    service_address_line1: Optional[str] = None
    service_address_line2: Optional[str] = None
    service_address_city: Optional[str] = None
    service_address_state: Optional[str] = None
    service_address_zip: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def require_at_least_one_update_field(self) -> UpdateCustomerArgs:
        update_fields = (
            "full_name",
            "phone_primary",
            "email",
            "service_address_line1",
            "service_address_line2",
            "service_address_city",
            "service_address_state",
            "service_address_zip",
            "notes",
        )
        if not any(getattr(self, field) is not None for field in update_fields):
            raise ValueError(
                "At least one field to update must be provided besides customer_id."
            )
        return self


class CreateEquipmentArgs(BaseModel):
    customer_id: str
    equipment_type: Literal[
        "AC_UNIT",
        "FURNACE",
        "HEAT_PUMP",
        "WATER_HEATER",
        "ELECTRICAL_PANEL",
        "PLUMBING_SYSTEM",
        "INTERNET_ROUTER",
        "OTHER",
    ]
    make: Optional[str] = None
    model: Optional[str] = None
    install_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    serial_number: Optional[str] = None
    known_issues: Optional[list[str]] = None


class UpdateDispatchArgs(BaseModel):
    job_id: str
    service_address_override: Optional[str] = None
    preferred_window: Optional[str] = None
    notes: Optional[str] = None
    cancel: Optional[bool] = False
