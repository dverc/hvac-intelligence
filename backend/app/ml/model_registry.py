"""Model versioning and artifact persistence for churn ML."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib

if TYPE_CHECKING:
    from app.ml.churn_model import ChurnModelEnsemble

logger = logging.getLogger(__name__)

DEFAULT_MODEL_VERSION = "latest"
_LEGACY_MODEL_FILENAME = "churn_model.pkl"

_ensemble: Any | None = None


def models_dir() -> Path:
    path = Path(__file__).resolve().parent / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _model_path(version: str) -> Path:
    if version in {DEFAULT_MODEL_VERSION, _LEGACY_MODEL_FILENAME.replace(".pkl", "")}:
        return models_dir() / _LEGACY_MODEL_FILENAME
    return models_dir() / f"{version}.pkl"


def _metrics_path(version: str) -> Path:
    if version in {DEFAULT_MODEL_VERSION, _LEGACY_MODEL_FILENAME.replace(".pkl", "")}:
        return models_dir() / "churn_model_metrics.json"
    return models_dir() / f"{version}_metrics.json"


def save_model(model: Any, version: str, metrics: dict[str, Any]) -> Path:
    """Persist model and metrics JSON sidecar."""
    target = _model_path(version)
    joblib.dump(model, target)

    payload = {
        **metrics,
        "version": version,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    _metrics_path(version).write_text(json.dumps(payload, indent=2))

    # Keep canonical latest copy in sync
    if version != _LEGACY_MODEL_FILENAME.replace(".pkl", ""):
        joblib.dump(model, models_dir() / _LEGACY_MODEL_FILENAME)
        (models_dir() / "churn_model_metrics.json").write_text(json.dumps(payload, indent=2))

    logger.info("Saved churn model version=%s to %s", version, target)
    return target


def load_model(version: str = DEFAULT_MODEL_VERSION) -> Any | None:
    """Load a versioned model; falls back to churn_model.pkl."""
    candidates = []
    if version == DEFAULT_MODEL_VERSION:
        candidates.append(models_dir() / _LEGACY_MODEL_FILENAME)
        versions = list_versions()
        if versions:
            candidates.insert(0, _model_path(versions[0]))
    else:
        candidates.append(_model_path(version))
        candidates.append(models_dir() / _LEGACY_MODEL_FILENAME)

    for path in candidates:
        if path.exists():
            try:
                return joblib.load(path)
            except Exception as exc:
                logger.warning("Failed to load model from %s: %s", path, exc)
    return None


def get_metrics(version: str = DEFAULT_MODEL_VERSION) -> dict[str, Any] | None:
    path = _metrics_path(version)
    if not path.exists() and version == DEFAULT_MODEL_VERSION:
        versions = list_versions()
        if versions:
            path = _metrics_path(versions[0])
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def list_versions() -> list[str]:
    """Return available model versions sorted by save time (newest first)."""
    root = models_dir()
    entries: list[tuple[float, str]] = []

    for path in root.glob("*.pkl"):
        name = path.stem
        if name == "churn_model":
            entries.append((path.stat().st_mtime, DEFAULT_MODEL_VERSION))
        else:
            entries.append((path.stat().st_mtime, name))

    entries.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    ordered: list[str] = []
    for _, version in entries:
        if version not in seen:
            seen.add(version)
            ordered.append(version)
    return ordered


def get_churn_ensemble() -> "ChurnModelEnsemble":
    """Lazy singleton — avoids reloading pickles per Celery task."""
    from app.ml.churn_model import ChurnModelEnsemble

    global _ensemble
    if _ensemble is None:
        _ensemble = ChurnModelEnsemble()
    return _ensemble
