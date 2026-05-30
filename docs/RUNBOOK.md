# HVAC Intelligence (Project Aero) — Operations Runbook

## Local development (end-to-end)

1. Copy environment template and set secrets:
   ```bash
   cp .env.example .env
   cp frontend/.env.local.example frontend/.env.local 2>/dev/null || true
   ```
   Set `POSTGRES_PASSWORD`, API keys (or leave Pinecone/OpenAI empty for mock RAG).

2. Start infrastructure and apps:
   ```bash
   docker compose up --build
   ```

3. Migrate and seed (host Python, with Postgres reachable on `localhost:5432`):
   ```bash
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   cd ..
   python scripts/seed_database.py
   ```

4. Verify API:
   ```bash
   curl -s http://localhost:8000/health | jq .
   open http://localhost:3000/dashboard
   ```

---

## Celery worker

**Docker Compose** (already defined):
```bash
docker compose up celery-worker
```

**Manual** (from `backend/` with `.env` loaded):
```bash
celery -A app.pipeline.celery_app worker -Q features,scoring -c 4 --loglevel=info
```

Queues: `features` (`process_call_features`), `scoring` (`batch_rescore_customers`).

---

## Kafka consumer (feature pipeline)

Consumes `KAFKA_TOPIC_CALL_FEATURES` (`call.features` by default), enqueues Celery `process_call_features`.

```bash
cd backend
python -m app.pipeline.kafka_consumer
```

If Kafka is down, `TranscriptService` falls back to `process_call_features.delay()` directly in dev.

---

## Index knowledge base (mock or Pinecone)

From repo root:
```bash
python scripts/index_knowledge_base.py \
  --namespace faq_general \
  --source data/knowledge/faqs/ \
  --mock
```

Without `--mock`, set `OPENAI_API_KEY` and `PINECONE_API_KEY` in `.env`. Mock index path: `RAG_MOCK_INDEX_PATH` (default `data/knowledge/.mock_vector_index.json`).

---

## Train churn model (when labeled data exists)

1. Ensure `feature_store` has rows and churn labels (see `ml/training/train_churn_model.py` SQL comments).
2. Uncomment and complete the training script sections.
3. Run from repo root:
   ```bash
   export DATABASE_URL=postgresql+psycopg2://hvac_user:changeme@localhost:5432/hvac_intel
   python ml/training/train_churn_model.py
   ```
4. Artifacts land in `MODEL_ARTIFACTS_PATH` (default `./ml/artifacts`). Restart backend/Celery to load new pickles.

---

## Manual batch rescore

**Celery task** (all active customers):
```bash
cd backend
celery -A app.pipeline.celery_app call app.pipeline.tasks.batch_rescore_customers
```

**Single customer** (API):
```bash
curl -X POST "http://localhost:8000/api/v1/churn/scores/{customer_id}/trigger"
```

SSE publishes `BATCH_SCORE_COMPLETE` when batch finishes (Redis pub/sub).

---

## Prometheus and Grafana

| Service    | URL (compose)        |
|-----------|----------------------|
| Prometheus | http://localhost:9090 |
| Grafana    | http://localhost:3001   (admin / `GRAFANA_PASSWORD`) |
| App metrics | http://localhost:8000/metrics |

Prometheus config: `infra/prometheus.yml` scrapes `backend:8000`.

Useful queries:
- Webhook rate: `rate(vapi_webhook_total[5m])`
- RAG p99: `histogram_quantile(0.99, rate(rag_retrieval_latency_seconds_bucket[5m]))`
- High-risk gauge: `high_risk_accounts_total`

---

## Common failure modes

| Symptom | Likely cause | Remediation |
|--------|--------------|-------------|
| `401` on `/webhook/vapi` | HMAC mismatch | Use raw JSON body; header `x-vapi-signature` = `sha256=<hex>` of body with `VAPI_WEBHOOK_SECRET`. |
| Churn always `model_not_trained` | Missing `ml/artifacts/*.pkl` | Train model or accept feature-only path until artifacts exist. |
| RAG returns empty | Index not built | Run `scripts/index_knowledge_base.py --mock`. |
| Celery tasks never run | Redis down / worker not started | `docker compose up redis celery-worker`; check `REDIS_URL`. |
| Features not scoring after call | Kafka consumer off | Start `kafka_consumer` or rely on dev Celery fallback on call-end. |
| SSE disconnects | Proxy timeout | Ingress annotations set 3600s for `/api/v1/stream/*`; ensure nginx buffering off for SSE. |
| Alembic fails on `vector` | pgvector missing | Use `pgvector/pgvector:pg16` image (compose/K8s Postgres). |
| Tests fail in CI | DB not migrated | Ensure `alembic upgrade head` before `pytest`; `hvac_intel_test` DB exists. |
| Frontend cannot reach API | Wrong `NEXT_PUBLIC_API_BASE_URL` | Set to public API origin at **build** time (Docker `ARG` / Vercel env). |

---

## Kubernetes deployment

1. Copy `infra/k8s/secrets.yaml.template` → `secrets.yaml`, replace each `REPLACE_ME` secret value.
2. GHCR images default to `ghcr.io/dverc/hvac-intelligence/backend` and `.../frontend`; `deploy.yml` retags on push to `main`.
3. `kubectl apply -f infra/k8s/namespace.yaml` then remaining manifests.
4. Set your production hostname in `infra/k8s/ingress.yaml` (`REPLACE_ME_DOMAIN` → e.g. `hvac.yourdomain.com`).

GitHub Actions: `ci.yml` on all pushes/PRs; `deploy.yml` on `main` (requires `KUBECONFIG` secret, optional `vars.NEXT_PUBLIC_API_BASE_URL`).
