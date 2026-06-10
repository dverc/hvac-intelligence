from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth_jwt import get_current_user
from app.ml.churn_model import resolve_scoring_method
from app.ml.drift_monitor import check_model_drift_async
from app.ml.model_registry import DEFAULT_MODEL_VERSION, get_churn_ensemble, get_metrics
from app.models.churn_score import ChurnScore
from app.models.ground_truth_label import GroundTruthLabel

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/model-health")
async def get_model_health(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict:
    """JWT-protected model quality and drift health snapshot."""
    metrics = get_metrics(DEFAULT_MODEL_VERSION) or get_metrics("v1") or {}
    model_version = str(metrics.get("version", "v1"))
    auc_roc = float(metrics.get("auc_roc", 0.0))
    ensemble = get_churn_ensemble()
    model = ensemble.calibrated_model if ensemble.is_ready else None
    scoring_method = resolve_scoring_method(model, metrics)
    model_quality = scoring_method

    drift = await check_model_drift_async(db, model_version=model_version)

    since = datetime.now(timezone.utc) - timedelta(days=30)
    total_scores_30d = (
        await db.scalar(
            select(func.count())
            .select_from(ChurnScore)
            .where(
                ChurnScore.entity_type == "CUSTOMER",
                ChurnScore.score_timestamp >= since,
            )
        )
    ) or 0

    ground_truth_labels_count = (
        await db.scalar(select(func.count()).select_from(GroundTruthLabel)) or 0
    )

    return {
        "model_version": model_version,
        "model_quality": model_quality,
        "auc_roc": round(auc_roc, 4),
        "drift_status": drift.get("status", "INSUFFICIENT_DATA"),
        "psi": float(drift.get("psi", 0.0)),
        "needs_retraining": bool(drift.get("needs_retraining", False)),
        "last_checked": drift.get("checked_at"),
        "scoring_method": scoring_method,
        "total_scores_30d": int(total_scores_30d),
        "ground_truth_labels_count": int(ground_truth_labels_count),
    }
