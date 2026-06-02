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
