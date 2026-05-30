from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from app.pipeline.sentiment_analyzer import SentimentAnalyzer


@dataclass
class CallFeatureVector:
    """Extracted features from a single completed call transcript."""

    call_id: str
    customer_id: str

    sentiment_overall: float
    sentiment_trajectory: list[dict]
    sentiment_degradation_slope: float
    anger_score: float
    frustration_score: float

    escalation_detected: bool
    recurrence_complaint_detected: bool
    complaint_keywords: list[str]

    pause_count: int
    avg_pause_ms: float
    filler_word_count: int

    duration_seconds: int
    call_outcome: str
    rag_queries_count: int
    tool_calls_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeatureExtractor:
    """
    Transforms Vapi transcript JSON into a CallFeatureVector.
    Input: transcript_json [{speaker, text, start_ms, end_ms, confidence, words?}]
    """

    RECURRENCE_KEYWORDS = [
        "third time",
        "again",
        "still broken",
        "keeps happening",
        "same problem",
        "not fixed",
        "didn't fix",
        "back again",
        "second time",
        "every year",
        "every summer",
    ]

    COMPLAINT_KEYWORDS = [
        "frustrated",
        "disappointed",
        "unacceptable",
        "ridiculous",
        "cancel",
        "refund",
        "never again",
        "worst",
        "terrible",
        "hot",
        "broken",
        "not working",
        "failed",
        "useless",
    ]

    def __init__(self, sentiment_analyzer: SentimentAnalyzer | None = None) -> None:
        self.sentiment = sentiment_analyzer or SentimentAnalyzer()

    def extract(
        self,
        call_id: str,
        customer_id: str,
        transcript_json: list[dict],
        call_metadata: dict,
    ) -> CallFeatureVector:
        customer_utterances = [
            t for t in transcript_json if t.get("speaker") == "customer"
        ]
        if not customer_utterances and transcript_json:
            customer_utterances = transcript_json

        full_text = " ".join([u.get("text", "") for u in customer_utterances])

        overall_sentiment = self.sentiment.analyze(full_text)
        trajectory = self._compute_sentiment_trajectory(customer_utterances)
        slope = self._compute_slope([p["score"] for p in trajectory])
        emotions = self.sentiment.classify_emotions(full_text)

        hesitation = self._extract_hesitation_markers(customer_utterances)

        text_lower = full_text.lower()
        recurrence_detected = any(kw in text_lower for kw in self.RECURRENCE_KEYWORDS)
        found_complaints = [kw for kw in self.COMPLAINT_KEYWORDS if kw in text_lower]

        tool_calls_log = call_metadata.get("tool_calls_log") or []
        if isinstance(tool_calls_log, str):
            tool_calls_count = 0
        else:
            tool_calls_count = len(tool_calls_log)

        return CallFeatureVector(
            call_id=call_id,
            customer_id=customer_id,
            sentiment_overall=float(overall_sentiment["compound"]),
            sentiment_trajectory=trajectory,
            sentiment_degradation_slope=slope,
            anger_score=float(emotions.get("anger", 0.0)),
            frustration_score=float(emotions.get("frustration", 0.0)),
            escalation_detected=bool(call_metadata.get("escalation_detected", False)),
            recurrence_complaint_detected=recurrence_detected,
            complaint_keywords=found_complaints,
            pause_count=hesitation["pause_count"],
            avg_pause_ms=hesitation["avg_pause_ms"],
            filler_word_count=hesitation["filler_word_count"],
            duration_seconds=int(call_metadata.get("duration_seconds", 0) or 0),
            call_outcome=str(call_metadata.get("call_outcome", "UNKNOWN")),
            rag_queries_count=int(call_metadata.get("rag_queries_issued", 0) or 0),
            tool_calls_count=tool_calls_count,
        )

    def _compute_sentiment_trajectory(self, utterances: list[dict]) -> list[dict]:
        """Score sentiment for each 60-second segment of the call."""
        if not utterances:
            return [{"minute": 0, "score": 0.0}]

        segments: dict[int, list[str]] = {}
        for utterance in utterances:
            start_ms = utterance.get("start_ms")
            if start_ms is None and utterance.get("words"):
                start_ms = utterance["words"][0].get("start_ms", 0)
            minute = int((start_ms or 0) // 60000)
            segments.setdefault(minute, []).append(utterance.get("text", ""))

        trajectory: list[dict] = []
        for minute in sorted(segments.keys()):
            text = " ".join(segments[minute])
            sentiment = self.sentiment.analyze(text)
            trajectory.append({"minute": minute, "score": float(sentiment["compound"])})

        if len(trajectory) <= 1 and len(utterances) >= 2:
            trajectory = []
            for index, utterance in enumerate(utterances):
                text = utterance.get("text", "")
                sentiment = self.sentiment.analyze(text)
                trajectory.append({"minute": index, "score": float(sentiment["compound"])})

        return trajectory or [{"minute": 0, "score": 0.0}]

    def _compute_slope(self, scores: list[float]) -> float:
        """OLS slope of sentiment scores over time. Negative slope = degrading sentiment."""
        if len(scores) < 2:
            return 0.0
        x = np.arange(len(scores))
        slope, _ = np.polyfit(x, np.array(scores, dtype=float), 1)
        return float(slope)

    def _extract_hesitation_markers(self, utterances: list[dict]) -> dict[str, int | float]:
        """
        Detect long pauses (>1000ms gap between consecutive words) and filler words.
        Requires word-level timestamps from Deepgram via Vapi transcript_json format.
        """
        filler_words = {"um", "uh", "like", "you know", "erm", "hmm"}
        pause_count = 0
        pause_durations: list[float] = []
        filler_count = 0

        for utterance in utterances:
            words = utterance.get("words", [])
            for index, word in enumerate(words):
                token = str(word.get("word", "")).lower().strip(".,!?")
                if token in filler_words:
                    filler_count += 1
            for index in range(1, len(words)):
                gap = words[index]["start_ms"] - words[index - 1]["end_ms"]
                if gap > 1000:
                    pause_count += 1
                    pause_durations.append(float(gap))

        return {
            "pause_count": pause_count,
            "avg_pause_ms": float(np.mean(pause_durations)) if pause_durations else 0.0,
            "filler_word_count": filler_count,
        }
