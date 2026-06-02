"""Call transcript API response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.call_transcript import CallTranscript


class TranscriptSummary(BaseModel):
    transcript_id: str
    call_id: str
    call_start_utc: str | None = None
    call_end_utc: str | None = None
    duration_seconds: int | None = None
    call_outcome: str | None = None
    vapi_end_reason: str | None = None
    call_cost_usd: float | None = None
    recording_url: str | None = None
    call_summary: str | None = None
    sentiment_overall: float | None = None
    sentiment_score: float | None = None
    transcript_raw: str | None = None
    transcript_json: list[Any] | dict[str, Any] | None = None
    tool_calls_log: list[Any] | None = None
    dispatch_job_id: str | None = None
    churn_risk_at_call_start: float | None = None
    intervention_successful: bool | None = None


class TranscriptDetail(TranscriptSummary):
    """Full transcript payload for a single call lookup."""


class CustomerTranscriptsResponse(BaseModel):
    customer_id: str
    transcripts: list[TranscriptSummary]


def transcript_to_summary(transcript: CallTranscript) -> TranscriptSummary:
    sentiment = (
        float(transcript.sentiment_overall)
        if transcript.sentiment_overall is not None
        else None
    )
    return TranscriptSummary(
        transcript_id=str(transcript.transcript_id),
        call_id=transcript.call_id,
        call_start_utc=transcript.call_start_utc.isoformat()
        if transcript.call_start_utc
        else None,
        call_end_utc=transcript.call_end_utc.isoformat()
        if transcript.call_end_utc
        else None,
        duration_seconds=transcript.duration_seconds,
        call_outcome=transcript.call_outcome,
        vapi_end_reason=transcript.vapi_end_reason,
        call_cost_usd=float(transcript.call_cost_usd)
        if transcript.call_cost_usd is not None
        else None,
        recording_url=transcript.recording_url,
        call_summary=transcript.call_summary,
        sentiment_overall=sentiment,
        sentiment_score=sentiment,
        transcript_raw=transcript.transcript_raw,
        transcript_json=transcript.transcript_json,
        tool_calls_log=transcript.tool_calls_log,
        dispatch_job_id=str(transcript.dispatch_job_id)
        if transcript.dispatch_job_id
        else None,
        churn_risk_at_call_start=float(transcript.churn_risk_at_call_start)
        if transcript.churn_risk_at_call_start is not None
        else None,
        intervention_successful=transcript.intervention_successful,
    )


def transcript_to_detail(transcript: CallTranscript) -> TranscriptDetail:
    return TranscriptDetail(**transcript_to_summary(transcript).model_dump())
