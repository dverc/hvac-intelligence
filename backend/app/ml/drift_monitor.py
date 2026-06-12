"""Population Stability Index (PSI) drift monitoring for churn scores."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ml.model_registry import get_metrics
from app.models.churn_score import ChurnScore

logger = logging.getLogger(__name__)

_EPS = 1e-6


def compute_psi(
    expected: list[float],
    actual: list[float],
    buckets: int = 10,
) -> float:
    """Population Stability Index between two score distributions."""
    if not expected or not actual or buckets < 1:
        return 0.0

    expected_arr = np.asarray(expected, dtype=float)
    actual_arr = np.asarray(actual, dtype=float)

    if expected_arr.size == 0 or actual_arr.size == 0:
        return 0.0

    exp_min = float(expected_arr.min())
    exp_max = float(expected_arr.max())

    if exp_min == exp_max:
        if float(actual_arr.min()) == exp_min and float(actual_arr.max()) == exp_min:
            return 0.0
        breakpoints = np.array([exp_min - _EPS, exp_max + _EPS], dtype=float)
    else:
        breakpoints = np.histogram_bin_edges(expected_arr, bins=buckets)

    expected_counts, _ = np.histogram(expected_arr, bins=breakpoints)
    actual_counts, _ = np.histogram(actual_arr, bins=breakpoints)

    expected_pct = expected_counts.astype(float) / max(len(expected_arr), 1)
    actual_pct = actual_counts.astype(float) / max(len(actual_arr), 1)

    mask = expected_counts > 0
    if not np.any(mask):
        return 0.0

    expected_pct = expected_pct[mask]
    actual_pct = actual_pct[mask]
    actual_pct = np.where(actual_pct == 0, _EPS, actual_pct)

    psi_values = (actual_pct - expected_pct) * np.log(actual_pct / expected_pct)
    return float(np.sum(psi_values))


def get_drift_status(psi: float) -> str:
    """Map PSI to drift severity label."""
    if psi < 0.1:
        return "STABLE"
    if psi <= 0.2:
        return "MONITOR"
    return "RETRAIN"


def compute_feature_drift(
    training_features: dict[str, list[float]],
    current_features: dict[str, list[float]],
) -> dict[str, float]:
    """Compute PSI per feature between training and current distributions."""
    results: dict[str, float] = {}
    all_keys = set(training_features) | set(current_features)
    for feature in all_keys:
        expected = training_features.get(feature, [])
        actual = current_features.get(feature, [])
        results[feature] = compute_psi(expected, actual)
    return results


def _evaluate_drift(
    expected_scores: list[float],
    actual_scores: list[float],
    *,
    model_version: str,
) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc)

    if len(actual_scores) < 10:
        return {
            "psi": 0.0,
            "status": "INSUFFICIENT_DATA",
            "needs_retraining": False,
            "checked_at": checked_at.isoformat(),
            "model_version": model_version,
            "recent_score_count": len(actual_scores),
        }

    if not expected_scores:
        return {
            "psi": 0.0,
            "status": "INSUFFICIENT_DATA",
            "needs_retraining": False,
            "checked_at": checked_at.isoformat(),
            "model_version": model_version,
            "recent_score_count": len(actual_scores),
        }

    psi = compute_psi(expected_scores, actual_scores)
    status = get_drift_status(psi)
    needs_retraining = status == "RETRAIN"

    result = {
        "psi": round(psi, 6),
        "status": status,
        "needs_retraining": needs_retraining,
        "checked_at": checked_at.isoformat(),
        "model_version": model_version,
        "recent_score_count": len(actual_scores),
    }

    from app.ml.mlflow_tracker import log_drift_check

    log_drift_check(model_version, psi, status, needs_retraining)
    return result


def _training_scores(model_version: str) -> list[float]:
    metrics = get_metrics(model_version) or get_metrics() or {}
    raw = metrics.get("training_scores", [])
    if not isinstance(raw, list):
        return []
    return [float(value) for value in raw]


def check_model_drift(
    db: Session,
    model_version: str = "v1",
    *,
    org_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Compare recent churn score distribution against training scores (sync)."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    churn_query = select(ChurnScore.churn_probability).where(
        ChurnScore.entity_type == "CUSTOMER",
        ChurnScore.score_timestamp >= since,
    )
    if org_id is not None:
        churn_query = churn_query.where(ChurnScore.org_id == org_id)
    rows = db.scalars(churn_query.order_by(ChurnScore.score_timestamp.desc())).all()

    actual_scores = [float(row) for row in rows]
    expected_scores = _training_scores(model_version)
    return _evaluate_drift(
        expected_scores,
        actual_scores,
        model_version=model_version,
    )


async def check_model_drift_async(
    db: AsyncSession,
    model_version: str = "v1",
) -> dict[str, Any]:
    """Async variant for FastAPI endpoints."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = (
        await db.execute(
            select(ChurnScore.churn_probability).where(
                ChurnScore.entity_type == "CUSTOMER",
                ChurnScore.score_timestamp >= since,
            )
        )
    ).scalars().all()

    actual_scores = [float(row) for row in rows]
    expected_scores = _training_scores(model_version)
    return _evaluate_drift(
        expected_scores,
        actual_scores,
        model_version=model_version,
    )
