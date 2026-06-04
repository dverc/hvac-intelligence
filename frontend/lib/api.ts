import type {
  ChurnDistributionResponse,
  ChurnScoreHistoryResponse,
  ChurnScoresListResponse,
  ChurnTimelineResponse,
  CohortHeatmapResponse,
  FeatureImportanceResponse,
  RetentionEventsResponse,
  SavedByAIResponse,
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
    headers: { Accept: "application/json", ...apiKeyHeaders() },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `GET ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { Accept: "application/json", ...apiKeyHeaders() },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `POST ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
}

async function apiPatch<T>(path: string, payload: CustomerUpdatePayload): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...apiKeyHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `PATCH ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
}

async function apiPatchJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...apiKeyHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `PATCH ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
}

async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "DELETE",
    cache: "no-store",
    headers: { Accept: "application/json", ...apiKeyHeaders() },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `DELETE ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
}

async function apiPostJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...apiKeyHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `POST ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
}

async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: { Accept: "application/json", ...apiKeyHeaders() },
    body: formData,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `POST ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
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
      ...apiKeyHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, `DELETE ${path} failed: ${body}`);
  }

  return response.json() as Promise<T>;
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

// ── SSE (dashboard real-time) ───────────────────────────────────────────────

/** URL for EventSource — not a JSON fetch. Auth via query param (SSE cannot set headers). */
export function getChurnEventsStreamUrl() {
  const url = new URL(`${getApiBaseUrl()}/api/v1/stream/churn-events`);
  const key = getPublicApiKey();
  if (key) {
    url.searchParams.set("api_key", key);
  }
  return url.toString();
}

// ── Helpers ─────────────────────────────────────────────────────────────────

export function defaultAnalyticsRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 90);
  return {
    start: start.toISOString(),
    end: end.toISOString(),
  };
}
