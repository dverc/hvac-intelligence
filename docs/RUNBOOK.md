# HVAC Intelligence (Project Aero) — Operations Runbook

> **Ground truth:** see [`docs/CURSOR_PROJECT_NOTES.md`](./CURSOR_PROJECT_NOTES.md) for verified DB state, API paths, and known bugs.

## Startup sequence (local)

1. `docker compose up -d postgres redis kafka zookeeper celery-worker celery-beat`
   - Postgres image: `pgvector/pgvector:pg16`
   - Typical running set: postgres, redis, kafka, zookeeper, celery-worker, celery-beat (6 containers)
2. `cd backend && alembic upgrade head` (head: `029_org_settings_constraints`)
3. `python scripts/seed_database.py` (repo root)
4. Optional: `python backend/scripts/migrate_pinecone_namespaces.py --mock`
5. `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
6. `cd frontend && npm run dev` — set `NEXT_PUBLIC_API_KEY` = `DASHBOARD_API_KEY` in `frontend/.env.local`
7. Optional tunnel: `ngrok http 8000` for Vapi/Google/Jobber OAuth callbacks.

**Login user is not seeded.** After a fresh DB, create admin via:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "X-API-Key: $DASHBOARD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"YourPass123!","org_id":"00000000-0000-4000-8000-000000000001","role":"admin"}'
```

If port 8000 is in use: `lsof -ti:8000 | xargs kill -9`

## Restart after a crash

1. Stop uvicorn/frontend (Ctrl+C or kill port 8000 / 3000).
2. `docker compose restart postgres redis`
3. Re-run migrations if schema changed: `cd backend && alembic upgrade head`
4. Start API and frontend again (steps 5–6 above).

## Database backup

```bash
docker compose exec -T postgres pg_dump -U hvac_user hvac_intel > backup_$(date +%Y%m%d).sql
```

Restore: `docker compose exec -T postgres psql -U hvac_user hvac_intel < backup.sql`

## Seed a new tenant

Two onboarding UIs (both functional):

| Route | Steps |
|-------|-------|
| `/dashboard/onboarding` | 6-step self-service: Business Details → Import Customers → Import Equipment → Knowledge Base → Configure Agent → Complete |
| `/dashboard/admin/onboarding/[org_id]` | 5-step admin wizard (after creating org in Organizations) |

API alternative (organizations):

```bash
curl -X POST http://localhost:8000/api/v1/organizations \
  -H "X-API-Key: $DASHBOARD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"org_name":"Acme HVAC","slug":"acme-hvac","industry":"hvac","business_phone":"+15551234567"}'
```

## Celery Beat schedules (8 tasks)

| Task | Schedule |
|------|----------|
| `sync_technician_schedules` | Every 2 hours |
| `batch_rescore_customers` | Daily 02:00 UTC |
| `sync_google_calendars` | Every 4 hours |
| `sync_jobber_data` | Every 6 hours |
| `sync_google_drive_folders` | Every 30 minutes |
| `send_weekly_client_reports` | Mondays 08:00 UTC |
| `check_model_drift_and_retrain` | Daily 03:00 UTC |
| `check_and_launch_campaigns` | Daily 10:00 UTC |

Start beat: `docker compose up -d celery-beat` or `cd backend && celery -A app.pipeline.celery_app beat --loglevel=info`

**Known bug:** beat tasks enqueue to the default `celery` queue, but `docker-compose.yml` runs the worker with `-Q features,scoring` only. Beat tasks (Jobber sync, outbound launcher, batch rescore, etc.) **will not run** until the worker also consumes `celery`. Fix: `-Q celery,features,scoring`. See `docs/CURSOR_PROJECT_NOTES.md`.

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
# Include celery queue so beat-scheduled tasks are consumed (see known bug above)
celery -A app.pipeline.celery_app worker -Q celery,features,scoring -c 4 --loglevel=info
```

Queues:

| Queue | Tasks |
|-------|-------|
| `features` | `process_call_features` |
| `scoring` | (reserved; most scoring uses default queue) |
| `celery` (default) | All beat tasks, `execute_outbound_campaign`, etc. |

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

## Dispatch / scheduling API

- **Router file:** `backend/app/api/v1/scheduling.py` (no `dispatch.py`)
- **Prefix:** `/api/v1/scheduling/*`
- **List jobs:** `GET /api/v1/scheduling/jobs?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`
- **Create jobs:** only via Vapi `schedule_dispatch` tool — there is no `POST /scheduling/jobs`

Dashboard dispatch board: `/dashboard/dispatch` · System health: `/dashboard/health` (not `/dashboard/system-health`).

---

## Auth & env vars

- JWT signing: **`JWT_SECRET_KEY`** (not `SECRET_KEY`)
- Dashboard API: requires **JWT Bearer + `X-API-Key`** on `/api/v1/*` (except portal, stream, webhooks)
- `users` table primary key column: **`id`** (not `user_id`)

---

## Common failure modes

| Symptom | Likely cause | Remediation |
|--------|--------------|-------------|
| `401` on `/webhook/vapi` | HMAC mismatch | Use raw JSON body; header `x-vapi-signature` = `sha256=<hex>` of body with `VAPI_WEBHOOK_SECRET`. |
| Churn always `model_not_trained` | Missing `ml/artifacts/*.pkl` | Train model or accept feature-only path until artifacts exist. |
| RAG returns empty | Index not built | Run `scripts/index_knowledge_base.py --mock`. |
| Celery tasks never run | Redis down / worker not started / wrong queue | `docker compose up redis celery-worker`; check `REDIS_URL`. Worker must listen on `celery` queue for beat tasks — use `-Q celery,features,scoring`. |
| Features not scoring after call | Kafka consumer off | Start `kafka_consumer` or rely on dev Celery fallback on call-end. |
| SSE disconnects | Proxy timeout | Ingress annotations set 3600s for `/api/v1/stream/*`; ensure nginx buffering off for SSE. |
| Alembic fails on `vector` | pgvector missing | Use `pgvector/pgvector:pg16` image (compose/K8s Postgres). |
| Tests fail in CI | DB not migrated | Ensure `alembic upgrade head` before `pytest`; `hvac_intel_test` DB exists. |
| Frontend cannot reach API | Wrong `NEXT_PUBLIC_API_BASE_URL` | Set to public API origin at **build** time (Docker `ARG` / Vercel env). |
| `ValidationError: DASHBOARD_API_KEY` | Missing env in CI/local | Set in `.env` and GitHub Actions `ci.yml` job env. |
| `connection refused` Postgres | Docker not running | `docker compose up -d postgres`; check `DATABASE_URL` host/port. |
| Celery worker missing | Service not started | `docker compose up -d celery-worker` or run worker manually. |
| Jobber/Google OAuth fails | Stale tunnel URL | Update redirect URIs in provider console to match ngrok host. |

---

## Kubernetes deployment

1. Copy `infra/k8s/secrets.yaml.template` → `secrets.yaml`, replace each `REPLACE_ME` secret value.
2. GHCR images default to `ghcr.io/dverc/hvac-intelligence/backend` and `.../frontend`; `deploy.yml` retags on push to `main`.
3. `kubectl apply -f infra/k8s/namespace.yaml` then remaining manifests.
4. Set your production hostname in `infra/k8s/ingress.yaml` (`REPLACE_ME_DOMAIN` → e.g. `hvac.yourdomain.com`).

GitHub Actions: `ci.yml` on all pushes/PRs; `deploy.yml` on `main` (requires `KUBECONFIG` secret, optional `vars.NEXT_PUBLIC_API_BASE_URL`).
