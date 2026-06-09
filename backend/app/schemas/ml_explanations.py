from __future__ import annotations

from pydantic import BaseModel, Field


class ShapFeatureExplanation(BaseModel):
    feature: str
    friendly_name: str
    value: float
    shap_value: float
    direction: str
    explanation: str


class ShapExplanationResponse(BaseModel):
    customer_id: str
    churn_probability: float
    baseline_probability: float
    features: list[ShapFeatureExplanation]
    top_risk_factors: list[str]
    top_protective_factors: list[str]


class CounterfactualItem(BaseModel):
    feature: str
    friendly_name: str
    current_value: float
    suggested_value: float
    suggested_action: str
    estimated_score_reduction: float


class CounterfactualResponse(BaseModel):
    customer_id: str
    current_score: float
    target_score: float
    interventions: list[CounterfactualItem]


class ChurnOutcomeRequest(BaseModel):
    churned: bool
    notes: str | None = None


class ChurnOutcomeResponse(BaseModel):
    status: str = "ok"
    customer_id: str
    churned: bool
    label_id: str
    churn_probability_at_time: float
    message: str = Field(default="Churn outcome recorded")
