import type { FeatureContribution, RiskTier } from "./churn";

export interface CustomerListItem {
  customer_id: string;
  full_name: string;
  phone_primary: string;
  account_status: string;
  risk_tier?: RiskTier;
}

export interface CustomerListResponse {
  page: number;
  limit: number;
  total: number;
  items: CustomerListItem[];
}

export interface OpenTicket {
  ticket_id: string;
  ticket_type: string;
  subject: string;
  priority: string;
  status: string;
  created_at: string;
}

export interface CustomerProfile {
  customer_id: string;
  external_id: string | null;
  full_name: string;
  phone_primary: string;
  email: string | null;
  account_status: string;
  customer_since: string;
  contract_type: string | null;
  contract_value_usd: number | null;
  address: {
    line1: string | null;
    line2: string | null;
    city: string | null;
    state: string | null;
    zip: string | null;
  };
  equipment: {
    equipment_id: string;
    make: string;
    model: string;
    equipment_type: string | null;
    age_years: number | null;
    last_service_date: string | null;
    warranty_expiry: string | null;
    known_issues: string[];
  }[];
  open_tickets: OpenTicket[];
  service_history_summary: {
    total_jobs: number;
    recent_jobs: {
      job_number: string;
      issue_type: string;
      job_status: string;
      priority: string;
      scheduled_window_start: string | null;
    }[];
  };
  churn: {
    customer_id: string;
    churn_probability: number;
    risk_tier: RiskTier;
    top_contributing_features: FeatureContribution[];
    recommended_interventions: string[];
    score_age_minutes: number;
    last_scored_at: string | null;
    model_version: string | null;
    source: string;
  };
}

/** Partial update body for PATCH /api/v1/customers/{id} */
export interface CustomerUpdatePayload {
  external_id?: string;
  full_name?: string;
  phone_primary?: string;
  phone_secondary?: string;
  email?: string;
  account_status?: "ACTIVE" | "SUSPENDED" | "CHURNED" | "PROSPECT";
  customer_since?: string;
  contract_type?: "ANNUAL_MAINTENANCE" | "RESIDENTIAL_OTC" | "COMMERCIAL_SLA";
  contract_value_usd?: number;
  payment_method?: string;
  preferred_tech_id?: string;
  notes?: string;
  address?: {
    line1?: string;
    line2?: string;
    city?: string;
    state?: string;
    zip?: string;
  };
}
