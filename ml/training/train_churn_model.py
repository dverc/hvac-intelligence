#!/usr/bin/env python3
"""
Offline training pipeline for the churn ensemble (§6 Phase 4).

Produces artifacts under ml/artifacts/:
  - xgb_churn_model.pkl
  - lgbm_churn_model.pkl
  - isolation_forest.pkl
  - feature_scaler.pkl
  - shap_explainer_xgb.pkl

Run from repo root after feature_store has labeled rows:
  python ml/training/train_churn_model.py
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Load feature_store table from PostgreSQL (90-day windows)
# ---------------------------------------------------------------------------
# import pandas as pd
# from sqlalchemy import create_engine, text
#
# DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg2")
# engine = create_engine(DATABASE_URL)
#
# FEATURE_COLS = [...]  # from app.ml.churn_schema.FEATURE_ORDER
#
# query = text("""
#     SELECT fs.*, c.account_status,
#            CASE WHEN c.account_status = 'CHURNED'
#                 AND c.updated_at <= fs.window_end + interval '90 days'
#                 THEN 1 ELSE 0 END AS churned_label
#     FROM feature_store fs
#     JOIN customers c ON c.customer_id = fs.entity_id
#     WHERE fs.entity_type = 'CUSTOMER'
#     ORDER BY fs.window_end ASC
# """)
# df = pd.read_sql(query, engine)
# X = df[FEATURE_COLS]
# y = df["churned_label"]

# ---------------------------------------------------------------------------
# 2. Ground truth labels: churned within 90 days of window_end
# ---------------------------------------------------------------------------
# (encoded in SQL above; adjust join to your churn definition)

# ---------------------------------------------------------------------------
# 3. Train/val/test split (70/15/15, time-based to prevent leakage)
# ---------------------------------------------------------------------------
# from sklearn.model_selection import train_test_split
#
# n = len(df)
# train_end = int(n * 0.70)
# val_end = int(n * 0.85)
# train_df = df.iloc[:train_end]
# val_df = df.iloc[train_end:val_end]
# test_df = df.iloc[val_end:]
#
# X_train, y_train = train_df[FEATURE_COLS], train_df["churned_label"]
# X_val, y_val = val_df[FEATURE_COLS], val_df["churned_label"]
# X_test, y_test = test_df[FEATURE_COLS], test_df["churned_label"]

# ---------------------------------------------------------------------------
# 4. Fit StandardScaler on train set
# ---------------------------------------------------------------------------
# from sklearn.preprocessing import StandardScaler
#
# scaler = StandardScaler()
# X_train_scaled = scaler.fit_transform(X_train)
# X_val_scaled = scaler.transform(X_val)
# X_test_scaled = scaler.transform(X_test)

# ---------------------------------------------------------------------------
# 5. Train XGBoost with Optuna hyperparameter search (50 trials, AUC-ROC)
# ---------------------------------------------------------------------------
# import optuna
# import xgboost as xgb
# from sklearn.metrics import roc_auc_score
#
# def xgb_objective(trial):
#     params = {
#         "max_depth": trial.suggest_int("max_depth", 3, 8),
#         "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
#         "n_estimators": trial.suggest_int("n_estimators", 100, 500),
#         "subsample": trial.suggest_float("subsample", 0.6, 1.0),
#         "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
#         "eval_metric": "auc",
#         "use_label_encoder": False,
#     }
#     model = xgb.XGBClassifier(**params)
#     model.fit(X_train_scaled, y_train, eval_set=[(X_val_scaled, y_val)], verbose=False)
#     preds = model.predict_proba(X_val_scaled)[:, 1]
#     return roc_auc_score(y_val, preds)
#
# study_xgb = optuna.create_study(direction="maximize")
# study_xgb.optimize(xgb_objective, n_trials=50)
# xgb_model = xgb.XGBClassifier(**study_xgb.best_params)
# xgb_model.fit(X_train_scaled, y_train)

# ---------------------------------------------------------------------------
# 6. Train LightGBM with Optuna (50 trials)
# ---------------------------------------------------------------------------
# import lightgbm as lgb
#
# def lgbm_objective(trial):
#     params = {
#         "num_leaves": trial.suggest_int("num_leaves", 16, 64),
#         "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
#         "n_estimators": trial.suggest_int("n_estimators", 100, 400),
#     }
#     model = lgb.LGBMClassifier(**params)
#     model.fit(X_train_scaled, y_train, eval_set=[(X_val_scaled, y_val)])
#     preds = model.predict_proba(X_val_scaled)[:, 1]
#     return roc_auc_score(y_val, preds)
#
# study_lgb = optuna.create_study(direction="maximize")
# study_lgb.optimize(lgbm_objective, n_trials=50)
# lgbm_model = lgb.LGBMClassifier(**study_lgb.best_params)
# lgbm_model.fit(X_train_scaled, y_train)

# ---------------------------------------------------------------------------
# 7. Fit IsolationForest on train features
# ---------------------------------------------------------------------------
# from sklearn.ensemble import IsolationForest
#
# isolation_forest = IsolationForest(contamination=0.05, random_state=42)
# isolation_forest.fit(X_train_scaled)

# ---------------------------------------------------------------------------
# 8. Calibrate probabilities (isotonic regression) — optional wrapper
# ---------------------------------------------------------------------------
# from sklearn.calibration import CalibratedClassifierCV
# calibrated_xgb = CalibratedClassifierCV(xgb_model, method="isotonic", cv=3)
# calibrated_xgb.fit(X_train_scaled, y_train)

# ---------------------------------------------------------------------------
# 9. Evaluate ensemble on test set: AUC-ROC, AUC-PR, Brier, F1@0.5
# ---------------------------------------------------------------------------
# from sklearn.metrics import (
#     average_precision_score,
#     brier_score_loss,
#     f1_score,
#     roc_auc_score,
# )
#
# ENSEMBLE_WEIGHTS = {"xgboost": 0.55, "lightgbm": 0.35, "isolation_forest": 0.10}
#
# def ensemble_proba(X_scaled):
#     xgb_p = xgb_model.predict_proba(X_scaled)[:, 1]
#     lgb_p = lgbm_model.predict_proba(X_scaled)[:, 1]
#     iso = isolation_forest.score_samples(X_scaled)
#     iso_norm = 1 - (iso - (-0.5)) / 1.0
#     iso_norm = iso_norm.clip(0, 1)
#     return (
#         xgb_p * ENSEMBLE_WEIGHTS["xgboost"]
#         + lgb_p * ENSEMBLE_WEIGHTS["lightgbm"]
#         + iso_norm * ENSEMBLE_WEIGHTS["isolation_forest"]
#     )
#
# test_probs = ensemble_proba(X_test_scaled)
# print("AUC-ROC", roc_auc_score(y_test, test_probs))
# print("AUC-PR", average_precision_score(y_test, test_probs))
# print("Brier", brier_score_loss(y_test, test_probs))
# print("F1@0.5", f1_score(y_test, (test_probs >= 0.5).astype(int)))

# ---------------------------------------------------------------------------
# 10. Compute SHAP explainer for XGBoost
# ---------------------------------------------------------------------------
# import shap
#
# shap_explainer = shap.Explainer(xgb_model, X_train_scaled)

# ---------------------------------------------------------------------------
# 11. Serialize artifacts to ml/artifacts/
# ---------------------------------------------------------------------------
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def serialize_artifacts(
    xgb_model,
    lgbm_model,
    isolation_forest,
    scaler,
    shap_explainer,
    output_dir: Path | None = None,
) -> None:
    output_dir = output_dir or ARTIFACTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "xgb_churn_model.pkl", "wb") as handle:
        pickle.dump(xgb_model, handle)
    with open(output_dir / "lgbm_churn_model.pkl", "wb") as handle:
        pickle.dump(lgbm_model, handle)
    with open(output_dir / "isolation_forest.pkl", "wb") as handle:
        pickle.dump(isolation_forest, handle)
    with open(output_dir / "feature_scaler.pkl", "wb") as handle:
        pickle.dump(scaler, handle)
    with open(output_dir / "shap_explainer_xgb.pkl", "wb") as handle:
        pickle.dump(shap_explainer, handle)

    print(f"Artifacts written to {output_dir}")


# ---------------------------------------------------------------------------
# 12. Log metrics to MLflow (optional)
# ---------------------------------------------------------------------------
# import mlflow
#
# mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
# with mlflow.start_run(run_name="churn_ensemble_v1"):
#     mlflow.log_metrics({"auc_roc": ..., "auc_pr": ..., "brier": ...})
#     mlflow.log_artifacts(str(ARTIFACTS_DIR))


def main() -> None:
    """
    Entry point — uncomment sections above once feature_store has labeled data.
    """
    artifacts_path = os.getenv("MODEL_ARTIFACTS_PATH", str(ARTIFACTS_DIR))
    print(
        "Training scaffold ready. Uncomment pipeline steps and provide labeled "
        f"feature_store rows, then write artifacts to {artifacts_path}"
    )


if __name__ == "__main__":
    main()
