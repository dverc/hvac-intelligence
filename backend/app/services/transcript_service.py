from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_transcript import CallTranscript
from app.pipeline.feature_extractor import FeatureExtractor
from app.pipeline.kafka_producer import publish_call_features
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)


class TranscriptService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._customers = CustomerService(db)
        self._churn = ChurnService(db)
        self._feature_extractor = FeatureExtractor()

    async def process_completed_call(self, call_data: dict[str, Any]) -> None:
        call = call_data.get("call", call_data)
        call_id = call.get("id") or call_data.get("call_id")
        if not call_id:
            return

        existing = await self.db.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )
        if existing.scalar_one_or_none() is not None:
            return

        phone = _extract_phone(call)
        customer_id: Optional[uuid.UUID] = None
        churn_start: Optional[float] = None
        if phone:
            customer = await self._customers.lookup_by_phone(phone)
            if customer:
                customer_id = customer.customer_id
                score = await self._churn.get_latest_score(str(customer.customer_id))
                churn_start = score.get("churn_probability")

        transcript_text = _extract_transcript_text(call_data)
        started, ended = _extract_timestamps(call)
        duration_seconds = (
            int((ended - started).total_seconds()) if ended and started else None
        )

        transcript_json = _normalize_transcript_json(
            call_data.get("transcript") or call.get("messages") or call_data.get("messages")
        )

        churn_end = churn_start
        intervention = False
        if churn_start is not None and churn_end is not None:
            intervention = (churn_start - churn_end) >= 0.15

        call_outcome = call_data.get("endedReason") or call.get("outcome") or "RETAINED"
        vapi_meta = dict(call_data.get("vapi_metadata") or call.get("metadata") or {})
        vapi_meta["raw_type"] = call_data.get("type")

        record = CallTranscript(
            call_id=call_id,
            customer_id=customer_id,
            call_direction="INBOUND",
            call_start_utc=started,
            call_end_utc=ended,
            duration_seconds=duration_seconds,
            call_outcome=call_outcome,
            transcript_raw=transcript_text,
            transcript_json=transcript_json,
            churn_risk_at_call_start=churn_start,
            churn_risk_at_call_end=churn_end,
            intervention_successful=intervention,
            vapi_metadata=vapi_meta,
        )

        if customer_id and transcript_json:
            call_features = self._extract_call_features(
                call_id=str(call_id),
                customer_id=str(customer_id),
                transcript_json=transcript_json,
                call_metadata={
                    "duration_seconds": duration_seconds or 0,
                    "call_outcome": call_outcome,
                    "escalation_detected": call_outcome == "ESCALATED_HUMAN",
                    "rag_queries_issued": int(vapi_meta.get("rag_queries_issued", 0) or 0),
                    "tool_calls_log": vapi_meta.get("tool_calls_log") or [],
                },
            )
            record.sentiment_overall = Decimal(str(call_features.sentiment_overall))
            record.sentiment_trajectory = call_features.sentiment_trajectory
            record.escalation_detected = call_features.escalation_detected
            record.hesitation_markers = {
                "pause_count": call_features.pause_count,
                "avg_pause_ms": call_features.avg_pause_ms,
                "filler_word_count": call_features.filler_word_count,
            }
            record.emotion_labels = {
                "anger": call_features.anger_score,
                "frustration": call_features.frustration_score,
            }
            record.rag_queries_issued = call_features.rag_queries_count
            record.tool_calls_log = vapi_meta.get("tool_calls_log")
            vapi_meta["recurrence_complaint_detected"] = (
                call_features.recurrence_complaint_detected
            )

            self.db.add(record)
            await self.db.flush()

            payload = {
                "call_id": str(call_id),
                "customer_id": str(customer_id),
                "entity_type": "CUSTOMER",
                "churn_risk_at_call_start": churn_start,
                "intervention_type": _infer_intervention_type(call_outcome, call_features),
                "call_features": call_features.to_dict(),
            }
            if not publish_call_features(payload):
                logger.info("Kafka unavailable; dispatching Celery task directly (dev fallback)")
                from app.pipeline.tasks import process_call_features

                process_call_features.delay(payload)
            return

        self.db.add(record)
        await self.db.flush()

    def _extract_call_features(
        self,
        call_id: str,
        customer_id: str,
        transcript_json: list[dict],
        call_metadata: dict[str, Any],
    ):
        return self._feature_extractor.extract(
            call_id=call_id,
            customer_id=customer_id,
            transcript_json=transcript_json,
            call_metadata=call_metadata,
        )


def _extract_phone(call: dict[str, Any]) -> Optional[str]:
    customer = call.get("customer") or {}
    if number := customer.get("number"):
        return str(number)
    if phone := call.get("phoneNumber"):
        if isinstance(phone, dict):
            return phone.get("number")
        return str(phone)
    return None


def _extract_transcript_text(call_data: dict[str, Any]) -> str:
    if text := call_data.get("transcript"):
        if isinstance(text, str):
            return text
    messages = call_data.get("messages") or call_data.get("artifact", {}).get("messages")
    if isinstance(messages, list):
        parts = []
        for msg in messages:
            if isinstance(msg, dict) and msg.get("message"):
                parts.append(str(msg["message"]))
            elif isinstance(msg, dict) and msg.get("content"):
                parts.append(str(msg["content"]))
        return " ".join(parts)
    return ""


def _normalize_transcript_json(raw: Any) -> list[dict]:
    """Map Vapi/Deepgram shapes to FeatureExtractor [{speaker, text, start_ms, words}]."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [{"speaker": "customer", "text": raw, "start_ms": 0}]

    normalized: list[dict] = []
    if not isinstance(raw, list):
        return normalized

    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("speaker")
        speaker = _role_to_speaker(role)
        text = item.get("text") or item.get("message") or item.get("content") or ""
        entry: dict[str, Any] = {
            "speaker": speaker,
            "text": str(text),
            "start_ms": item.get("start_ms") or item.get("time") or 0,
            "end_ms": item.get("end_ms"),
            "confidence": item.get("confidence"),
        }
        if words := item.get("words"):
            entry["words"] = words
        normalized.append(entry)
    return normalized


def _role_to_speaker(role: Any) -> str:
    if role in ("user", "customer", "caller"):
        return "customer"
    if role in ("assistant", "bot", "agent", "system"):
        return "agent"
    return str(role) if role else "unknown"


def _infer_intervention_type(call_outcome: str, call_features) -> str:
    if call_outcome == "DISPATCHED":
        return "PRIORITY_DISPATCH"
    if call_outcome == "ESCALATED_HUMAN":
        return "MANAGER_CALLBACK"
    if call_features.escalation_detected:
        return "COMPLAINT_ESCALATION"
    return "VOICE_RETENTION"


def _extract_timestamps(call: dict[str, Any]) -> tuple[datetime, Optional[datetime]]:
    now = datetime.now(timezone.utc)
    started = call.get("startedAt") or call.get("startTime")
    ended = call.get("endedAt") or call.get("endTime")

    def _parse(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    start_dt = _parse(started) or now
    end_dt = _parse(ended)
    return start_dt, end_dt
