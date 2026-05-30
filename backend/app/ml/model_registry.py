"""Lazy singleton for churn model — avoids reloading pickles per Celery task."""

from __future__ import annotations

from app.ml.churn_model import ChurnModelEnsemble

_ensemble: ChurnModelEnsemble | None = None


def get_churn_ensemble() -> ChurnModelEnsemble:
    global _ensemble
    if _ensemble is None:
        _ensemble = ChurnModelEnsemble()
    return _ensemble
