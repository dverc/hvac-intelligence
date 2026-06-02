export interface TranscriptSummary {
  transcript_id: string;
  call_id: string;
  call_start_utc: string | null;
  call_end_utc: string | null;
  duration_seconds: number | null;
  call_outcome: string | null;
  vapi_end_reason: string | null;
  call_cost_usd: number | null;
  recording_url: string | null;
  call_summary: string | null;
  sentiment_overall: number | null;
  sentiment_score: number | null;
  transcript_raw: string | null;
  transcript_json: TranscriptMessage[] | Record<string, unknown> | null;
  tool_calls_log: unknown[] | null;
  dispatch_job_id: string | null;
  churn_risk_at_call_start: number | null;
  intervention_successful: boolean | null;
}

export interface TranscriptMessage {
  role?: string;
  speaker?: string;
  message?: string;
  text?: string;
  content?: string;
}

export type TranscriptDetail = TranscriptSummary;

export interface CustomerTranscriptsResponse {
  customer_id: string;
  transcripts: TranscriptSummary[];
}
