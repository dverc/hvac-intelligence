# Pre-Production Checklist

> Ops ground truth: [`docs/CURSOR_PROJECT_NOTES.md`](./CURSOR_PROJECT_NOTES.md) (Celery queue bug, auth, scheduling API).

Gate criteria from §6 Phase 8. Status reflects what has been verified in this repository build (Phases 0–8), not production load testing.

| # | Criterion | Status | How to verify |
|---|-----------|--------|---------------|
| 1 | All Phase 7 tests pass with **>90% coverage** on `services/` and `pipeline/` | ☐ | `cd backend && pytest tests/ --cov=app.services --cov=app.pipeline --cov-report=term-missing` — current suite: **28 tests**, **~60% overall** `app` coverage; services/pipeline sub-packages are below 90%. |
| 2 | Churn model **AUC-ROC ≥ 0.78** on held-out test set (logged to MLflow) | ☐ | Train artifacts: `python ml/training/train_churn_model.py` (scaffold). Confirm `ml/artifacts/*.pkl` exist and MLflow run reports `auc_roc >= 0.78`. |
| 3 | Vapi webhook **p99 latency < 200ms** (tool execution excluded) | ☐ | `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{handler="/webhook/vapi"}[5m])) by (le))` in Prometheus, or load-test with `hey` against `/webhook/vapi` with signed payloads. |
| 4 | RAG retrieval **p99 latency < 800ms** | ☐ | `histogram_quantile(0.99, rate(rag_retrieval_latency_seconds_bucket[5m]))` after exercising `search_knowledge_base` tool calls. |
| 5 | SSE stream stable **1h+** under **50 concurrent** connections | ☐ | `for i in $(seq 50); do curl -N "http://localhost:8000/api/v1/stream/churn-events" & done; wait` — monitor disconnects and backend CPU for ≥1h. |
| 6 | Feature pipeline processes `call.features` with **< 30s end-to-end lag** | ☐ | Publish a test message to Kafka topic `call.features` (or complete a Vapi call-end webhook) and compare `call_transcripts.call_ended_at` to latest `churn_scores.score_timestamp` for the customer. |
| 7 | Churn re-scoring completes within **6-hour SLA** on **500-account** corpus | ☐ | `celery -A app.pipeline.celery_app call app.pipeline.tasks.batch_rescore_customers` on a DB with ≥500 customers; measure wall time vs `SCORING_CADENCE_HOURS=6`. **Prerequisite:** Celery worker must consume `celery` queue (`-Q celery,features,scoring`) or beat-scheduled rescore never runs. |
| 8 | Grafana dashboard live with all **key metrics** instrumented | ☐ Partial | Six Prometheus metrics in `app/core/metrics.py` exposed at `/metrics`; Prometheus + Grafana in `docker-compose.yml`. Import or build a dashboard covering: `vapi_webhook_total`, `tool_execution_latency_seconds`, `churn_scoring_latency_seconds`, `high_risk_accounts_total`, `saved_by_ai_total`, `rag_retrieval_latency_seconds`. |
| 9 | Database migrations **idempotent** and tested against production schema clone | ☑ Partial | `cd backend && alembic upgrade head` on fresh Postgres (CI runs this). Head: `029_org_settings_constraints` (29 migrations). For prod clone: restore snapshot → `alembic upgrade head` → confirm no errors. |
| 10 | Secrets via **AWS Secrets Manager / Vault** (no `.env` in production) | ☐ Partial | K8s template: `infra/k8s/secrets.yaml.template`. Production: populate secret store, sync to `hvac-intelligence-secrets`, never commit real `secrets.yaml`. |

## Quick smoke (before demo / recruiter review)

- [ ] `docker compose up --build` → `curl -sf http://localhost:8000/health` returns 200
- [ ] `python scripts/index_knowledge_base.py --namespace faq_general --source data/knowledge/faqs/ --mock`
- [ ] Postman: signed `POST /webhook/vapi` call-end → features in `feature_store` / churn row or `model_not_trained`
- [ ] Push to GitHub → **CI** workflow green on `ci.yml`
