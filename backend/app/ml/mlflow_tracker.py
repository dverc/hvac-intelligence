"""Optional MLflow experiment tracking — no-ops when MLflow is unavailable."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_MLFLOW_AVAILABLE: bool | None = None


def _mlflow_enabled() -> bool:
    global _MLFLOW_AVAILABLE
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        return False
    if _MLFLOW_AVAILABLE is None:
        try:
            import mlflow  # noqa: F401

            _MLFLOW_AVAILABLE = True
        except ImportError:
            _MLFLOW_AVAILABLE = False
    return bool(_MLFLOW_AVAILABLE)


def log_training_run(
    model_version: str,
    metrics: dict[str, Any],
    params: dict[str, Any],
    feature_names: list[str],
) -> str | None:
    """Log a training run to MLflow when configured."""
    if not _mlflow_enabled():
        return None

    try:
        import mlflow

        mlflow.set_experiment("hvac_churn_model")
        with mlflow.start_run(run_name=f"churn_{model_version}") as run:
            for key, value in params.items():
                mlflow.log_param(key, value)
            for key in ("auc_roc", "precision", "recall", "f1", "accuracy"):
                if key in metrics:
                    mlflow.log_metric(key, float(metrics[key]))
            mlflow.set_tag("model_version", model_version)
            mlflow.set_tag("feature_names", ",".join(feature_names))
            return run.info.run_id
    except Exception as exc:
        logger.debug("MLflow training log skipped: %s", exc)
        return None


def log_drift_check(
    model_version: str,
    psi: float,
    status: str,
    needs_retraining: bool,
) -> None:
    """Log drift check results to MLflow when configured."""
    if not _mlflow_enabled():
        return

    try:
        import mlflow

        mlflow.set_experiment("hvac_churn_drift")
        with mlflow.start_run(run_name=f"drift_{model_version}"):
            mlflow.log_metric("psi", float(psi))
            mlflow.set_tag("drift_status", status)
            mlflow.set_tag("needs_retraining", str(needs_retraining))
            mlflow.set_tag("model_version", model_version)
    except Exception as exc:
        logger.debug("MLflow drift log skipped: %s", exc)


def get_best_run(metric: str = "auc_roc") -> dict[str, Any] | None:
    """Return the best MLflow run by metric if MLflow is available."""
    if not _mlflow_enabled():
        return None

    try:
        import mlflow
        from mlflow.entities import ViewType

        experiment = mlflow.get_experiment_by_name("hvac_churn_model")
        if experiment is None:
            return None

        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string="",
            run_view_type=ViewType.ACTIVE_ONLY,
            order_by=[f"metrics.{metric} DESC"],
            max_results=1,
        )
        if runs.empty:
            return None

        row = runs.iloc[0]
        return {
            "run_id": row.get("run_id"),
            "metric": metric,
            "value": float(row.get(f"metrics.{metric}", 0.0)),
            "model_version": row.get("tags.model_version"),
        }
    except Exception as exc:
        logger.debug("MLflow best run lookup skipped: %s", exc)
        return None
