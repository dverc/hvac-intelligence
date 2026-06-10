"""Automated retraining triggers driven by drift monitoring."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.drift_monitor import check_model_drift
from app.models.ground_truth_label import GroundTruthLabel

logger = logging.getLogger(__name__)

_GROUND_TRUTH_MINIMUM = 20


def check_and_trigger_retraining(db: Session) -> dict:
    """Evaluate drift and optionally trigger batch rescoring."""
    drift = check_model_drift(db)
    psi = float(drift.get("psi", 0.0))

    if drift.get("status") == "INSUFFICIENT_DATA":
        return {
            "triggered": False,
            "reason": "insufficient_data",
            "psi": psi,
        }

    if not drift.get("needs_retraining"):
        return {
            "triggered": False,
            "reason": "stable",
            "psi": psi,
        }

    ground_truth_count = db.scalar(
        select(func.count()).select_from(GroundTruthLabel)
    ) or 0

    if ground_truth_count < _GROUND_TRUTH_MINIMUM:
        return {
            "triggered": False,
            "reason": "insufficient_ground_truth",
            "psi": psi,
        }

    from app.pipeline.tasks import batch_rescore_customers

    batch_rescore_customers.delay()
    logger.info("Automated retraining triggered due to drift (PSI=%.3f)", psi)
    return {
        "triggered": True,
        "reason": "drift",
        "psi": psi,
    }
