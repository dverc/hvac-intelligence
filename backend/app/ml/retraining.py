"""Automated retraining triggers driven by drift monitoring."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.drift_monitor import check_model_drift
from app.models.ground_truth_label import GroundTruthLabel

logger = logging.getLogger(__name__)

_GROUND_TRUTH_MINIMUM = 20


def _load_training_data_from_labels(
    db: Session,
    org_id: str,
) -> list[tuple[dict[str, Any], int]]:
    org_uuid = uuid.UUID(str(org_id))
    rows = db.scalars(
        select(GroundTruthLabel)
        .where(GroundTruthLabel.org_id == org_uuid)
        .order_by(GroundTruthLabel.recorded_at.asc())
    ).all()
    training: list[tuple[dict[str, Any], int]] = []
    for row in rows:
        snapshot = row.feature_snapshot or {}
        if not snapshot:
            continue
        training.append((dict(snapshot), int(row.churned)))
    return training


def train_model_from_ground_truth(db: Session, org_id: str) -> dict[str, Any]:
    """Train and persist a new churn model from labeled outcomes for one org."""
    from app.ml.churn_model import train_model
    from app.ml.model_registry import reset_churn_ensemble, save_model

    training_data = _load_training_data_from_labels(db, org_id)
    if len(training_data) < _GROUND_TRUTH_MINIMUM:
        return {
            "status": "skipped",
            "reason": "insufficient_ground_truth",
            "sample_count": len(training_data),
        }

    model, metrics = train_model(training_data)
    version = f"v_auto_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    save_model(model, version, metrics)
    reset_churn_ensemble()
    logger.info(
        "Trained churn model version=%s for org_id=%s from %s ground-truth labels (AUC=%.3f)",
        version,
        org_id,
        len(training_data),
        float(metrics.get("auc_roc", 0.0)),
    )
    return {
        "status": "ok",
        "model_version": version,
        "sample_count": len(training_data),
        "auc_roc": float(metrics.get("auc_roc", 0.0)),
    }


def check_and_trigger_retraining(db: Session, org_id: str) -> dict[str, Any]:
    """Evaluate drift for one org; train and batch-rescore when RETRAIN + enough labels."""
    org_uuid = uuid.UUID(str(org_id))
    drift = check_model_drift(db, org_id=org_uuid)
    psi = float(drift.get("psi", 0.0))
    status = str(drift.get("status", "STABLE"))

    if status == "INSUFFICIENT_DATA":
        logger.info(
            "Drift check: insufficient score data (status=%s, PSI=%.3f)",
            status,
            psi,
        )
        return {
            "triggered": False,
            "reason": "insufficient_data",
            "psi": psi,
            "status": status,
        }

    if status == "STABLE":
        logger.info("Drift check: model stable (PSI=%.3f); no action", psi)
        return {
            "triggered": False,
            "reason": "stable",
            "psi": psi,
            "status": status,
        }

    if status == "MONITOR":
        logger.warning(
            "Drift check: MONITOR band (PSI=%.3f); logging only, not retraining",
            psi,
        )
        return {
            "triggered": False,
            "reason": "monitor",
            "psi": psi,
            "status": status,
        }

    ground_truth_count = int(
        db.scalar(
            select(func.count())
            .select_from(GroundTruthLabel)
            .where(GroundTruthLabel.org_id == org_uuid)
        )
        or 0
    )

    if ground_truth_count < _GROUND_TRUTH_MINIMUM:
        logger.warning(
            "Retraining skipped: drift=%s PSI=%.3f but only %s ground-truth "
            "labels (need %s)",
            status,
            psi,
            ground_truth_count,
            _GROUND_TRUTH_MINIMUM,
        )
        return {
            "triggered": False,
            "reason": "insufficient_ground_truth",
            "psi": psi,
            "status": status,
            "ground_truth_count": ground_truth_count,
        }

    try:
        train_result = train_model_from_ground_truth(db, org_id)
        if train_result.get("status") != "ok":
            logger.warning(
                "Retraining aborted after drift=%s: %s",
                status,
                train_result.get("reason"),
            )
            return {
                "triggered": False,
                "reason": train_result.get("reason", "training_skipped"),
                "psi": psi,
                "status": status,
                "ground_truth_count": ground_truth_count,
            }

        from app.pipeline.tasks import batch_rescore_customers

        batch_rescore_customers.delay()
        logger.info(
            "Automated retraining triggered: trained %s, queued batch rescoring "
            "(drift=%s, PSI=%.3f, labels=%s)",
            train_result.get("model_version"),
            status,
            psi,
            ground_truth_count,
        )
        return {
            **train_result,
            "triggered": True,
            "reason": "drift",
            "psi": psi,
            "status": status,
            "org_id": org_id,
            "ground_truth_count": ground_truth_count,
        }
    except Exception as exc:
        logger.exception(
            "Automated retraining failed (drift=%s, PSI=%.3f): %s",
            status,
            psi,
            exc,
        )
        return {
            "triggered": False,
            "reason": "training_failed",
            "psi": psi,
            "status": status,
            "ground_truth_count": ground_truth_count,
            "error": str(exc),
        }
