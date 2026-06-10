export type RiskTier = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export const RISK_COLORS: Record<RiskTier, string> = {
  LOW: "#22c55e",
  MEDIUM: "#f59e0b",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};

export interface FeatureContribution {
  feature: string;
  shap_value: number;
  direction: "INCREASES_RISK" | "DECREASES_RISK";
}

export interface ShapFeatureExplanation {
  feature: string;
  friendly_name: string;
  value: number;
  shap_value: number;
  direction: "INCREASES_RISK" | "DECREASES_RISK";
  explanation: string;
}

export interface ShapExplanationResponse {
  customer_id: string;
  churn_probability: number;
  baseline_probability: number;
  features: ShapFeatureExplanation[];
  top_risk_factors: string[];
  top_protective_factors: string[];
}

export type DriftStatus = "STABLE" | "MONITOR" | "RETRAIN" | "INSUFFICIENT_DATA";
export type ScoringMethod = "rule_based" | "ml_model";

export interface ModelHealthResponse {
  model_version: string;
  model_quality: ScoringMethod;
  auc_roc: number;
  drift_status: DriftStatus;
  psi: number;
  needs_retraining: boolean;
  last_checked: string | null;
  scoring_method: ScoringMethod;
  total_scores_30d: number;
  ground_truth_labels_count: number;
}

export interface CounterfactualIntervention {
  feature: string;
  friendly_name: string;
  current_value: number;
  suggested_value: number;
  suggested_action: string;
  estimated_score_reduction: number;
}

export interface CounterfactualResponse {
  customer_id: string;
  current_score: number;
  target_score: number;
  interventions: CounterfactualIntervention[];
}

export interface ChurnScore {
  churn_probability: number;
  risk_tier: RiskTier;
  feature_contributions: FeatureContribution[];
  model_version: string;
  score_age_minutes: number;
  last_scored_at: string;
}

export interface ChurnTimelinePoint {
  timestamp: string;
  churn_probability: number;
  risk_tier: RiskTier;
  event?: {
    type:
      | "CALL_START"
      | "DISPATCH_CREATED"
      | "INTERVENTION_APPLIED"
      | "TICKET_RESOLVED"
      | "CHURNED";
    label: string;
    call_id?: string;
  };
}

export interface ChurnTimelineResponse {
  customer_id: string;
  customer_name: string;
  data_points: ChurnTimelinePoint[];
  current_score: number;
  score_90d_ago: number;
  net_change: number;
  interventions_count: number;
  saved_by_ai: boolean;
}

export interface SavedByAIResponse {
  period_start: string;
  period_end: string;
  total_high_risk_calls: number;
  successful_interventions: number;
  intervention_success_rate: number;
  estimated_arr_retained_usd: number;
  avg_score_reduction: number;
  monthly_trend: {
    month: string;
    interventions: number;
    arr_retained_usd: number;
    success_rate: number;
  }[];
  top_intervention_types: {
    type: string;
    count: number;
    avg_score_reduction: number;
  }[];
}

export interface SSEChurnEvent {
  event_type: "CALL_ACTIVE" | "INTERVENTION_COMPLETE" | "BATCH_SCORE_COMPLETE";
  call_id?: string;
  customer_id?: string;
  customer_name?: string;
  churn_risk_tier?: RiskTier;
  churn_probability?: number;
  score_before?: number;
  score_after?: number;
  delta?: number;
  saved_by_ai?: boolean;
  intervention_type?: string;
  job_number?: string;
  accounts_scored?: number;
  new_critical?: number;
  resolved_critical?: number;
  timestamp: string;
}

// §5.1.1 — GET /api/v1/analytics/churn-probability-distribution
export interface ChurnDistributionResponse {
  as_of: string;
  total_customers: number;
  cohorts: {
    tier: RiskTier;
    count: number;
    percentage: number;
    avg_score: number;
    estimated_arr_at_risk_usd: number;
  }[];
  week_over_week_delta: {
    tier: string;
    delta_count: number;
    delta_percentage: number;
  }[];
}

// §5.1.3 — GET /api/v1/churn/cohorts
export interface CohortHeatmapResponse {
  generated_at: string;
  buckets: {
    score_range_low: number;
    score_range_high: number;
    customer_count: number;
    avg_arr_usd: number;
    intervention_success_rate: number;
    top_features: string[];
    customers_sample: {
      customer_id: string;
      name: string;
      score: number;
    }[];
  }[];
}

// GET /api/v1/analytics/retention-events
export interface RetentionEventsResponse {
  period_start: string;
  period_end: string;
  events: {
    event_id: string;
    timestamp: string;
    event_type:
      | "CALL_START"
      | "INTERVENTION_APPLIED"
      | "DISPATCH_CREATED"
      | "SCORE_CHANGE"
      | "TICKET_RESOLVED"
      | "CHURNED";
    customer_id: string;
    customer_name: string;
    label: string;
    call_id?: string;
    churn_probability_before?: number;
    churn_probability_after?: number;
    risk_tier?: string;
    saved_by_ai: boolean;
  }[];
}

// GET /api/v1/analytics/feature-importance
export interface FeatureImportanceResponse {
  model_version: string | null;
  as_of: string;
  source: "aggregated_churn_scores" | "no_contributions";
  features: {
    feature: string;
    importance: number;
    avg_shap_value: number;
    direction: "INCREASES_RISK" | "DECREASES_RISK";
  }[];
}

export interface ChurnScoreListItem {
  score_id: string;
  entity_type: string;
  entity_id: string;
  churn_probability: number;
  risk_tier: RiskTier;
  score_timestamp: string;
}

export interface ChurnScoresListResponse {
  items: ChurnScoreListItem[];
}

export interface ChurnScoreHistoryResponse {
  entity_id: string;
  days: number;
  history: {
    churn_probability: number;
    risk_tier: RiskTier;
    score_timestamp: string;
  }[];
}
