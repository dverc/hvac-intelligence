from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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
