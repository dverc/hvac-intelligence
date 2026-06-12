import type {
  ChurnDistributionResponse,
  ChurnScoreHistoryResponse,
  ChurnScoresListResponse,
  ChurnTimelineResponse,
  CohortHeatmapResponse,
  CounterfactualResponse,
  FeatureImportanceResponse,
  RetentionEventsResponse,
  SavedByAIResponse,
  ModelHealthResponse,
  ShapExplanationResponse,
} from "@/types/churn";
import type {
  CustomerListResponse,
  CustomerProfile,
  CustomerUpdatePayload,
} from "@/types/customer";
import type {
  CustomerTranscriptsResponse,
  TranscriptDetail,
} from "@/types/transcript";

import { getPublicApiKey } from "@/lib/config";

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function apiKeyHeaders(): Record<string, string> {
  const key = getPublicApiKey();
  if (!key) {
    return {};
  }
  return { "X-API-Key": key };
}

function authenticatedHeaders(): Record<string, string> {
  const headers = { ...apiKeyHeaders() };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("hvac_token");
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }
  return headers;
}

async function parseApiResponse<T>(
  response: Response,
  path: string,
  method: string,
): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("hvac_token");
        localStorage.removeItem("hvac_org_id");
        window.location.href = "/login";
      }
      throw new ApiError(401, "Unauthorized");
    }
    const body = await response.text();
    throw new ApiError(response.status, `${method} ${path} failed: ${body}`);
  }
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
): Promise<T> {
  const url = new URL(`${getApiBaseUrl()}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await fetch(url.toString(), {
    cache: "no-store",
    headers: { Accept: "application/json", ...authenticatedHeaders() },
  });

  return parseApiResponse<T>(response, path, "GET");
}

async function apiPost<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { Accept: "application/json", ...authenticatedHeaders() },
  });

  return parseApiResponse<T>(response, path, "POST");
}

async function apiPatch<T>(path: string, payload: CustomerUpdatePayload): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authenticatedHeaders(),
    },
    body: JSON.stringify(payload),
  });

  return parseApiResponse<T>(response, path, "PATCH");
}

async function apiPatchJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authenticatedHeaders(),
    },
    body: JSON.stringify(payload),
  });

  return parseApiResponse<T>(response, path, "PATCH");
}

async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "DELETE",
    cache: "no-store",
    headers: { Accept: "application/json", ...authenticatedHeaders() },
  });

  return parseApiResponse<T>(response, path, "DELETE");
}

async function apiPostJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authenticatedHeaders(),
    },
    body: JSON.stringify(payload),
  });

  return parseApiResponse<T>(response, path, "POST");
}

async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { Accept: "application/json", ...authenticatedHeaders() },
    body: formData,
  });

  return parseApiResponse<T>(response, path, "POST");
}

// ── Churn ─────────────────────────────────────────────────────────────────────

export function listChurnScores(params?: {
  entity_type?: string;
  risk_tier?: string;
  limit?: number;
}) {
  return apiGet<ChurnScoresListResponse>("/api/v1/churn/scores", {
    entity_type: params?.entity_type ?? "CUSTOMER",
    risk_tier: params?.risk_tier,
    limit: params?.limit ?? 50,
  });
}

export function getChurnScoreHistory(entityId: string, days = 90) {
  return apiGet<ChurnScoreHistoryResponse>(
    `/api/v1/churn/scores/${entityId}/history`,
    { days },
  );
}

export function triggerChurnScore(entityId: string) {
  return apiPost<{ status: string; entity_id: string }>(
    `/api/v1/churn/scores/${entityId}/trigger`,
  );
}

export function getChurnCohorts(windowDays = 90, bucketCount = 10) {
  return apiGet<CohortHeatmapResponse>("/api/v1/churn/cohorts", {
    window_days: windowDays,
    bucket_count: bucketCount,
  });
}

// ── Customers ───────────────────────────────────────────────────────────────

export function listCustomers(params?: {
  search?: string;
  page?: number;
  limit?: number;
}) {
  return apiGet<CustomerListResponse>("/api/v1/customers", {
    search: params?.search,
    page: params?.page ?? 1,
    limit: params?.limit ?? 50,
  });
}

export function getCustomer(customerId: string) {
  return apiGet<CustomerProfile>(`/api/v1/customers/${customerId}`);
}

export function updateCustomer(customerId: string, payload: CustomerUpdatePayload) {
  return apiPatch<CustomerProfile>(`/api/v1/customers/${customerId}`, payload);
}

export function getCustomerTranscripts(customerId: string) {
  return apiGet<CustomerTranscriptsResponse>(
    `/api/v1/customers/${customerId}/transcripts`,
  );
}

export function getCallDetail(callId: string) {
  return apiGet<TranscriptDetail>(`/api/v1/calls/${callId}`);
}

export type {
  CustomerTranscriptsResponse,
  TranscriptDetail,
  TranscriptSummary,
} from "@/types/transcript";

export function getCustomerChurnTimeline(customerId: string) {
  return apiGet<ChurnTimelineResponse>(
    `/api/v1/customers/${customerId}/churn-timeline`,
  );
}

async function apiGetAuthenticated<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json", ...authenticatedHeaders() },
  });
  return parseApiResponse<T>(response, path, "GET");
}

export function getCustomerShapExplanation(customerId: string) {
  return apiGetAuthenticated<ShapExplanationResponse>(
    `/api/v1/customers/${customerId}/shap-explanation`,
  );
}

export function getCustomerCounterfactuals(customerId: string) {
  return apiGetAuthenticated<CounterfactualResponse>(
    `/api/v1/customers/${customerId}/counterfactuals`,
  );
}

export function getModelHealth() {
  return apiGet<ModelHealthResponse>("/api/v1/ml/model-health");
}

/** Client-side mirror of backend get_disclosure_text — always includes AI + recording disclosure. */
export function buildDisclosureText(
  orgDisplayName: string,
  disclosureStyle: string,
): string {
  const name = orgDisplayName.trim() || "Your HVAC Company";
  if (disclosureStyle.toUpperCase() === "FORMAL") {
    return (
      `This call is being handled by an artificial intelligence system on behalf of ${name}. ` +
      "This call is recorded. You have the right to speak with a human representative at any time."
    );
  }
  return (
    `Hi, this is an AI virtual assistant calling on behalf of ${name}. ` +
    "This call may be recorded for quality assurance."
  );
}

// ── Analytics ───────────────────────────────────────────────────────────────

export function getChurnProbabilityDistribution() {
  return apiGet<ChurnDistributionResponse>(
    "/api/v1/analytics/churn-probability-distribution",
  );
}

export function getRetentionEvents(start: string, end: string) {
  return apiGet<RetentionEventsResponse>("/api/v1/analytics/retention-events", {
    start,
    end,
  });
}

export function getSavedByAI(start: string, end: string) {
  return apiGet<SavedByAIResponse>("/api/v1/analytics/saved-by-ai", {
    start,
    end,
  });
}

export function getFeatureImportance(modelVersion = "latest") {
  return apiGet<FeatureImportanceResponse>("/api/v1/analytics/feature-importance", {
    model_version: modelVersion,
  });
}

export interface CallAnalyticsResponse {
  summary: {
    total_calls: number;
    calls_booked: number;
    calls_escalated: number;
    calls_abandoned: number;
    booking_rate: number;
    avg_duration_seconds: number;
    total_cost_usd: number;
  };
  revenue_impact: {
    estimated_bookings_value_usd: number;
    ai_cost_usd: number;
    roi_multiplier: number;
  };
  calls_by_day: { date: string; count: number }[];
  calls_by_hour: { hour: number; count: number }[];
  top_issue_types: { issue_type: string; count: number }[];
  sentiment_breakdown: {
    positive: number;
    neutral: number;
    negative: number;
  };
}

export function getCallAnalytics(days = 30) {
  return apiGet<CallAnalyticsResponse>("/api/v1/analytics/calls", { days });
}

// ── Knowledge base ────────────────────────────────────────────────────────────

export interface KnowledgeDocument {
  doc_id: string;
  document_id: string;
  filename: string;
  namespace: string;
  chunk_count: number;
  file_size_bytes?: number;
  mime_type?: string;
  uploaded_at: string;
  last_indexed_at: string;
}

export interface KnowledgeDocumentsResponse {
  org_id: string;
  total: number;
  items: KnowledgeDocument[];
}

export interface ServiceCatalogItem {
  service_id: string;
  org_id: string;
  service_code: string;
  service_name: string;
  category: string;
  description?: string;
  base_price_usd?: number | string;
  price_max_usd?: number | string;
  price_notes?: string;
  duration_minutes_min?: number;
  duration_minutes_max?: number;
  is_active: boolean;
  requires_equipment_type?: string;
  emergency_surcharge_pct?: number | string;
  created_at: string;
  updated_at: string;
}

export interface ServiceCatalogResponse {
  org_id: string;
  total: number;
  items: ServiceCatalogItem[];
}

export function getKnowledgeDocuments(orgId: string) {
  return apiGet<KnowledgeDocumentsResponse>(`/api/v1/knowledge/${orgId}/documents`);
}

export function uploadKnowledgeDocument(orgId: string, formData: FormData) {
  return apiPostForm<{ document_id: string; chunks_indexed: number; namespace: string }>(
    `/api/v1/knowledge/${orgId}/documents`,
    formData,
  );
}

export function deleteKnowledgeDocument(orgId: string, documentId: string) {
  return apiDelete<{ deleted: boolean; document_id: string }>(
    `/api/v1/knowledge/${orgId}/documents/${documentId}`,
  );
}

export function getServiceCatalog(orgId: string) {
  return apiGet<ServiceCatalogResponse>(`/api/v1/knowledge/${orgId}/service-catalog`);
}

export function createServiceItem(orgId: string, data: Record<string, unknown>) {
  return apiPostJson<ServiceCatalogItem>(
    `/api/v1/knowledge/${orgId}/service-catalog`,
    data,
  );
}

export function updateServiceItem(
  orgId: string,
  serviceId: string,
  data: Record<string, unknown>,
) {
  return apiPatchJson<ServiceCatalogItem>(
    `/api/v1/knowledge/${orgId}/service-catalog/${serviceId}`,
    data,
  );
}

// ── Scheduling / dispatch ─────────────────────────────────────────────────────

export interface ScheduledJob {
  job_id: string;
  job_number: string;
  customer_id: string;
  customer_name: string;
  issue_type: string;
  issue_description?: string;
  technician_id?: string;
  technician_name?: string;
  priority: string;
  job_status: string;
  scheduled_window_start?: string;
  scheduled_window_end?: string;
}

export interface ScheduledJobsResponse {
  org_id: string;
  total: number;
  items: ScheduledJob[];
}

export interface AvailabilitySlot {
  date: string;
  start_time: string;
  end_time: string;
  technician_id: string;
  technician_name: string;
  slot_label: string;
}

export function getScheduledJobs(
  dateFrom: string,
  dateTo: string,
  technicianId?: string,
  status?: string,
) {
  return apiGet<ScheduledJobsResponse>("/api/v1/scheduling/jobs", {
    date_from: dateFrom,
    date_to: dateTo,
    technician_id: technicianId,
    status,
  });
}

export function getAvailability(
  dateFrom: string,
  dateTo: string,
  technicianId?: string,
  durationMinutes = 60,
) {
  return apiGet<AvailabilitySlot[]>("/api/v1/scheduling/availability", {
    date_from: dateFrom,
    date_to: dateTo,
    technician_id: technicianId,
    duration_minutes: durationMinutes,
  });
}

// ── Integrations (Google Calendar) ──────────────────────────────────────────

export type GoogleCalendarEntry = {
  token_id?: string;
  email: string;
  calendar_id: string;
  technician_id: string | null;
  is_active: boolean;
  token_expiry?: string | null;
};

export type GoogleCalendarStatus = {
  connected: boolean;
  calendars: GoogleCalendarEntry[];
};

export function getGoogleCalendarStatus(orgId: string) {
  return apiGet<GoogleCalendarStatus>("/api/v1/integrations/google/status", {
    org_id: orgId,
  });
}

export function getGoogleConnectUrl(orgId: string, technicianId?: string) {
  return apiGet<{ authorization_url: string }>(
    "/api/v1/integrations/google/connect",
    { org_id: orgId, technician_id: technicianId },
  );
}

export function syncGoogleCalendar(
  orgId: string,
  technicianId: string,
  dateFrom: string,
  dateTo: string,
) {
  void orgId;
  return apiPostJson<{ synced: number }>("/api/v1/integrations/google/sync", {
    technician_id: technicianId,
    date_from: dateFrom,
    date_to: dateTo,
  });
}

export function disconnectGoogleCalendar(orgId: string, email: string) {
  void orgId;
  return apiDeleteJson<{ disconnected: boolean }>(
    "/api/v1/integrations/google/disconnect",
    { google_account_email: email },
  );
}

async function apiDeleteJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "DELETE",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authenticatedHeaders(),
    },
    body: JSON.stringify(payload),
  });

  return parseApiResponse<T>(response, path, "DELETE");
}

// ── Integrations (Jobber) ───────────────────────────────────────────────────

export type JobberStatus = {
  connected: boolean;
  account_name: string | null;
  account_id: string | null;
  last_sync_at: string | null;
  is_active: boolean;
};

export function getJobberStatus(orgId: string) {
  return apiGet<JobberStatus>("/api/v1/integrations/jobber/status", {
    org_id: orgId,
  });
}

export function getJobberConnectUrl(orgId: string) {
  return apiGet<{ authorization_url: string }>(
    "/api/v1/integrations/jobber/connect",
    { org_id: orgId },
  );
}

export function syncJobberData(
  orgId: string,
  syncType: "all" | "clients" | "jobs" | "users" = "all",
  daysAhead = 7,
) {
  void orgId;
  return apiPostJson<{
    clients_synced: number;
    users_synced: number;
    jobs_synced: number;
  }>("/api/v1/integrations/jobber/sync", {
    sync_type: syncType,
    days_ahead: daysAhead,
  });
}

export function disconnectJobber(orgId: string) {
  void orgId;
  return apiDeleteJson<{ disconnected: boolean }>(
    "/api/v1/integrations/jobber/disconnect",
    {},
  );
}

// ── Organizations (admin) ───────────────────────────────────────────────────

export type OrganizationRecord = {
  org_id: string;
  org_name: string;
  slug: string;
  industry: string;
  business_phone: string | null;
  vapi_assistant_id: string | null;
  vapi_phone_number_id: string | null;
  plan_tier: string;
  is_active: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  customer_count?: number;
};

export type OrganizationCreatePayload = {
  org_name: string;
  slug: string;
  industry: string;
  business_phone?: string;
  vapi_assistant_id?: string;
  vapi_phone_number_id?: string;
  plan_tier?: string;
  is_active?: boolean;
  settings?: Record<string, unknown>;
};

export function getOrganizations() {
  return apiGet<OrganizationRecord[]>("/api/v1/organizations");
}

export function createOrganization(data: OrganizationCreatePayload) {
  return apiPostJson<OrganizationRecord>("/api/v1/organizations", data);
}

export type OnboardingProvisionPayload = {
  business_name: string;
  trade_type: string;
  phone_number: string;
  agent_name: string;
  timezone: string;
  business_hours: Record<string, { open: string; close: string } | null>;
  notification_email: string;
  service_zip_codes?: string[];
};

export type OnboardingProvisionResponse = {
  org_id: string;
  org_name: string;
  slug: string;
  agent_name: string;
  dashboard_api_key: string;
};

export function provisionOnboarding(data: OnboardingProvisionPayload) {
  return apiPostJson<OnboardingProvisionResponse>(
    "/api/v1/onboarding/provision",
    data,
  );
}

export function updateOrganizationSettings(
  orgId: string,
  settings: Record<string, unknown>,
) {
  return apiPatchJson<OrganizationRecord>(`/api/v1/organizations/${orgId}`, {
    settings,
  });
}

// ── Admin onboarding (multi-tenant) ─────────────────────────────────────────

export type OrgSettingsRecord = {
  setting_id: string;
  org_id: string;
  display_name: string | null;
  phone_display: string | null;
  address_line1: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  agent_greeting: string | null;
  agent_name: string;
  business_hours_start: number;
  business_hours_end: number;
  timezone: string;
  vapi_assistant_id: string | null;
  vapi_phone_number_id: string | null;
  vapi_phone_number: string | null;
  outbound_enabled: boolean;
  outbound_disclosure_style: string;
  max_outbound_attempts: number;
  onboarding_completed: boolean;
  onboarding_step: number;
  created_at: string;
  updated_at: string;
};

export type AdminOrganizationListItem = {
  org_id: string;
  org_name: string;
  slug: string;
  industry: string;
  plan_tier: string;
  is_active: boolean;
  status: "ACTIVE" | "TRIAL" | "INACTIVE";
  user_count: number;
  technician_count: number;
  onboarding_completed: boolean;
  onboarding_step: number;
  display_name: string | null;
  created_at: string;
};

export type AdminOrganizationDetail = {
  org_id: string;
  org_name: string;
  slug: string;
  industry: string;
  business_phone: string | null;
  plan_tier: string;
  is_active: boolean;
  status: "ACTIVE" | "TRIAL" | "INACTIVE";
  user_count: number;
  technician_count: number;
  settings: OrgSettingsRecord | null;
  created_at: string;
  updated_at: string;
};

export function listAdminOrganizations() {
  return apiGet<AdminOrganizationListItem[]>("/api/v1/admin/organizations");
}

export function createAdminOrganization(payload: {
  company_name: string;
  admin_email: string;
  admin_first_name?: string;
  admin_last_name?: string;
  industry?: string;
  plan_tier?: string;
}) {
  return apiPostJson<{
    org_id: string;
    org_name: string;
    slug: string;
    settings: OrgSettingsRecord;
    admin_user_id: string | null;
    temporary_password: string | null;
  }>("/api/v1/admin/organizations", payload);
}

export function getAdminOrganization(orgId: string) {
  return apiGet<AdminOrganizationDetail>(`/api/v1/admin/organizations/${orgId}`);
}

export function updateAdminOrganization(
  orgId: string,
  payload: Record<string, unknown>,
) {
  return apiPatchJson<AdminOrganizationDetail>(
    `/api/v1/admin/organizations/${orgId}`,
    payload,
  );
}

export function createAdminOrgUser(
  orgId: string,
  payload: {
    email: string;
    first_name?: string;
    last_name?: string;
    role?: string;
  },
) {
  return apiPostJson<{
    user_id: string;
    email: string;
    role: string;
    org_id: string;
    temporary_password: string;
  }>(`/api/v1/admin/organizations/${orgId}/users`, payload);
}

export function listAdminOrgUsers(orgId: string) {
  return apiGet<
    {
      user_id: string;
      email: string;
      role: string;
      org_id: string;
      is_active: boolean;
      created_at: string;
      last_login_at: string | null;
    }[]
  >(`/api/v1/admin/organizations/${orgId}/users`);
}

export type AdminTechnicianRecord = {
  technician_id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  specialty: string | null;
  employment_status: string;
};

export function listAdminOrgTechnicians(orgId: string) {
  return apiGet<AdminTechnicianRecord[]>(
    `/api/v1/admin/organizations/${orgId}/technicians`,
  );
}

export function createAdminOrgTechnician(
  orgId: string,
  payload: {
    full_name: string;
    phone?: string;
    email?: string;
    specialty?: string;
  },
) {
  return apiPostJson<AdminTechnicianRecord>(
    `/api/v1/admin/organizations/${orgId}/technicians`,
    payload,
  );
}

export function getAdminOnboarding(orgId: string) {
  return apiGet<{
    org_id: string;
    onboarding_completed: boolean;
    onboarding_step: number;
    display_name: string | null;
  }>(`/api/v1/admin/organizations/${orgId}/onboarding`);
}

export function updateAdminOnboarding(
  orgId: string,
  payload: { onboarding_step?: number; onboarding_completed?: boolean },
) {
  return apiPatchJson<{
    org_id: string;
    onboarding_completed: boolean;
    onboarding_step: number;
    display_name: string | null;
  }>(`/api/v1/admin/organizations/${orgId}/onboarding`, payload);
}

export function provisionAdminOrganization(orgId: string) {
  return apiPostJson<{
    org_id: string;
    settings: OrgSettingsRecord;
    example_customer_created: boolean;
  }>(`/api/v1/admin/organizations/${orgId}/provision`, {});
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/health`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

export type SystemHealthResponse = {
  status: "healthy" | "degraded" | "unhealthy";
  timestamp: string;
  components: Record<
    string,
    { status: string; latency_ms?: number; vector_count?: number; last_call_at?: string; error?: string }
  >;
  metrics: {
    total_organizations: number;
    total_customers: number;
    total_calls_today: number;
    total_dispatch_jobs_open: number;
  };
};

export function getSystemHealth() {
  return apiGet<SystemHealthResponse>("/api/v1/system/health");
}

// ── Outbound campaigns ──────────────────────────────────────────────────────

export type OutboundCampaign = {
  campaign_id: string;
  org_id: string;
  campaign_name: string;
  campaign_type: string;
  status: string;
  churn_score_threshold: number;
  max_attempts: number;
  calling_hours_start: number;
  calling_hours_end: number;
  disclosure_style: string;
  total_customers_targeted: number;
  total_calls_made: number;
  total_consented: number;
  total_booked: number;
  created_at: string;
  updated_at: string;
  conversion_rate: number;
};

export type BlockedAttempt = {
  attempt_id: string;
  customer_id: string;
  customer_name: string;
  block_reason: string;
  notes: string | null;
  timestamp: string;
};

export function listOutboundCampaigns() {
  return apiGet<OutboundCampaign[]>("/api/v1/outbound/campaigns");
}

export function createOutboundCampaign(payload: Record<string, unknown>) {
  return apiPostJson<OutboundCampaign>("/api/v1/outbound/campaigns", payload);
}

export function previewEligibleCustomers(
  churnScoreThreshold: number,
  maxAttempts: number,
) {
  return apiGet<{ eligible_count: number; churn_score_threshold: number }>(
    "/api/v1/outbound/campaigns/preview-eligible",
    { churn_score_threshold: churnScoreThreshold, max_attempts: maxAttempts },
  );
}

export function updateOutboundCampaignStatus(
  campaignId: string,
  status: string,
) {
  return apiPatchJson<OutboundCampaign>(
    `/api/v1/outbound/campaigns/${campaignId}/status`,
    { status },
  );
}

export function executeOutboundCampaign(campaignId: string) {
  return apiPostJson<{ status: string; message: string; campaign_id: string }>(
    `/api/v1/outbound/campaigns/${campaignId}/execute`,
    {},
  );
}

export function listBlockedAttempts() {
  return apiGet<BlockedAttempt[]>("/api/v1/outbound/compliance/blocked");
}

export function getDisclosurePreview(disclosureStyle: string) {
  return apiGet<{ display_name: string; disclosure_text: string }>(
    "/api/v1/outbound/compliance/disclosure-preview",
    { disclosure_style: disclosureStyle },
  );
}

// ── Data import (CSV + Google Drive) ────────────────────────────────────────

export type CsvImportResult = {
  total_rows: number;
  imported: number;
  skipped: number;
  errors: { row: number; message: string }[];
  dry_run: boolean;
  warnings: string[];
};

export type DriveStatus = {
  connected: boolean;
  folder_id: string | null;
  folder_url: string | null;
  file_count: number;
  last_sync: string | null;
};

export function importCustomers(orgId: string, file: File, dryRun: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("dry_run", dryRun ? "true" : "false");
  return apiPostForm<CsvImportResult>(
    `/api/v1/imports/${orgId}/customers`,
    form,
  );
}

export function importEquipment(orgId: string, file: File, dryRun: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("dry_run", dryRun ? "true" : "false");
  return apiPostForm<CsvImportResult>(
    `/api/v1/imports/${orgId}/equipment`,
    form,
  );
}

export async function getImportTemplate(
  orgId: string,
  type: "customers" | "equipment",
): Promise<Blob> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/imports/${orgId}/templates/${type}`,
    {
      cache: "no-store",
      headers: { ...authenticatedHeaders() },
    },
  );
  if (!response.ok) {
    if (response.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("hvac_token");
        localStorage.removeItem("hvac_org_id");
        window.location.href = "/login";
      }
      throw new ApiError(401, "Unauthorized");
    }
    const body = await response.text();
    throw new ApiError(
      response.status,
      `GET template ${type} failed: ${body}`,
    );
  }
  return response.blob();
}

export function setupDriveFolder(orgId: string) {
  return apiPost<{ folder_id: string; folder_url: string; message: string }>(
    `/api/v1/imports/${orgId}/drive/setup`,
  );
}

export function syncDriveFolder(orgId: string) {
  return apiPost<{ synced: number; skipped: number; errors: number }>(
    `/api/v1/imports/${orgId}/drive/sync`,
  );
}

export function getDriveStatus(orgId: string) {
  return apiGet<DriveStatus>(`/api/v1/imports/${orgId}/drive/status`);
}

// ── SSE (dashboard real-time) ───────────────────────────────────────────────

/** One-time short-lived token for EventSource (SSE cannot set auth headers). */
export async function fetchChurnEventsSseToken(): Promise<string | null> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/stream/sse-token`, {
      method: "POST",
      cache: "no-store",
      headers: { Accept: "application/json", ...authenticatedHeaders() },
    });
    if (!response.ok) {
      console.error("[SSE] Failed to fetch stream token:", response.status);
      return null;
    }
    const data = (await response.json()) as { token: string };
    return data.token;
  } catch (err) {
    console.error("[SSE] Failed to fetch stream token:", err);
    return null;
  }
}

/** URL for EventSource — uses a one-time SSE token from `fetchChurnEventsSseToken`. */
export function getChurnEventsStreamUrl(sseToken: string) {
  const url = new URL(`${getApiBaseUrl()}/api/v1/stream/churn-events`);
  url.searchParams.set("token", sseToken);
  return url.toString();
}

// ── Helpers ─────────────────────────────────────────────────────────────────

// ── Customer portal (public, no auth) ───────────────────────────────────────

export interface PortalAppointment {
  id: string;
  scheduled_window_start: string | null;
  scheduled_window_end: string | null;
  issue_type: string;
  issue_description: string | null;
  job_status: string;
  technician_name: string | null;
  job_number: string;
}

export interface PortalIdentifyResult {
  found: boolean;
  customer_id?: string;
  name?: string;
  upcoming_appointments: PortalAppointment[];
  past_appointments: PortalAppointment[];
}

export interface PortalAppointmentsResult {
  customer_id: string;
  name: string;
  upcoming_appointments: PortalAppointment[];
  past_appointments: PortalAppointment[];
}

async function portalFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `${init?.method ?? "GET"} ${path} failed: ${body}`);
  }
  return response.json() as Promise<T>;
}

export function portalIdentify(phone: string) {
  return portalFetch<PortalIdentifyResult>("/api/v1/portal/identify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
}

export function portalGetAppointments(customerId: string) {
  return portalFetch<PortalAppointmentsResult>(
    `/api/v1/portal/appointments/${customerId}`,
  );
}

export function portalRequestService(payload: {
  phone: string;
  name?: string;
  issue_type: string;
  description?: string;
  preferred_date?: string;
  preferred_time_window?: string;
}) {
  return portalFetch<{ success: boolean; ticket_number: string; message: string }>(
    "/api/v1/portal/request",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function portalRescheduleRequest(payload: {
  customer_id: string;
  appointment_id: string;
  preferred_date: string;
  preferred_time_window: string;
  reason?: string;
}) {
  return portalFetch<{ success: boolean; message: string }>(
    "/api/v1/portal/reschedule-request",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function defaultAnalyticsRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 90);
  return {
    start: start.toISOString(),
    end: end.toISOString(),
  };
}
