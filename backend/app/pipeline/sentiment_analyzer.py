from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Lexicon fallback for classify_emotions (offline-friendly; no extra HF model download).
ANGER_LEXICON = {
    "angry",
    "furious",
    "outraged",
    "mad",
    "rage",
    "hate",
    "livid",
}
FRUSTRATION_LEXICON = {
    "frustrated",
    "frustrating",
    "annoyed",
    "annoying",
    "ridiculous",
    "unacceptable",
    "disappointed",
    "fed up",
    "sick of",
}
SATISFACTION_LEXICON = {
    "thank",
    "thanks",
    "appreciate",
    "great",
    "excellent",
    "happy",
    "pleased",
    "wonderful",
    "perfect",
}


class SentimentAnalyzer:
    """
    Sentiment for call transcripts.
    - analyze(): distilbert-base-uncased-finetuned-sst-2-english (§6 Phase 4)
    - classify_emotions(): lexicon-based probabilities (dev default)
    """

    MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"

    def __init__(self) -> None:
        self._pipeline: Any | None = None

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from transformers import pipeline

            logger.info("Loading sentiment model %s", self.MODEL_NAME)
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.MODEL_NAME,
                truncation=True,
            )
        return self._pipeline

    def analyze(self, text: str) -> dict[str, float | str]:
        if not text or not text.strip():
            return {"compound": 0.0, "label": "NEUTRAL"}

        try:
            clf = self._get_pipeline()
            # Truncate very long calls for transformer limits
            chunk = text[:4000]
            result = clf(chunk)[0]
            label_raw = str(result["label"]).upper()
            score = float(result["score"])
            if label_raw == "POSITIVE":
                compound = score
                label = "POSITIVE"
            elif label_raw == "NEGATIVE":
                compound = -score
                label = "NEGATIVE"
            else:
                compound = 0.0
                label = label_raw
            return {"compound": compound, "label": label}
        except Exception as exc:
            logger.warning("Transformer sentiment failed, using lexicon fallback: %s", exc)
            return self._lexicon_sentiment(text)

    def classify_emotions(self, text: str) -> dict[str, float]:
        """Lexicon-based emotion scores normalized to sum to 1.0."""
        lower = text.lower()
        tokens = set(re.findall(r"[a-z']+", lower))
        text_blob = lower

        anger_hits = sum(1 for w in ANGER_LEXICON if w in tokens or w in text_blob)
        frustration_hits = sum(
            1 for w in FRUSTRATION_LEXICON if w in tokens or w in text_blob
        )
        satisfaction_hits = sum(
            1 for w in SATISFACTION_LEXICON if w in tokens or w in text_blob
        )

        raw = {
            "anger": float(anger_hits),
            "frustration": float(frustration_hits),
            "satisfaction": float(satisfaction_hits),
            "neutral": 1.0,
        }
        total = sum(raw.values())
        if total <= 0:
            return {"anger": 0.0, "frustration": 0.0, "satisfaction": 0.0, "neutral": 1.0}
        return {k: v / total for k, v in raw.items()}

    @staticmethod
    def _lexicon_sentiment(text: str) -> dict[str, float | str]:
        emotions = SentimentAnalyzer().classify_emotions(text)
        if emotions["anger"] + emotions["frustration"] > emotions["satisfaction"]:
            compound = -min(1.0, emotions["anger"] + emotions["frustration"])
            label = "NEGATIVE"
        elif emotions["satisfaction"] > 0.4:
            compound = emotions["satisfaction"]
            label = "POSITIVE"
        else:
            compound = 0.0
            label = "NEUTRAL"
        return {"compound": compound, "label": label}
