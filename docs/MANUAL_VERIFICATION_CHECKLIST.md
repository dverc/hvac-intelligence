# Manual Verification Checklist (Outside Cursor)

Last audited: **2026-06-04** (Vapi tools re-checked same day — 12/12 linked).

Only **remaining** manual steps are listed below. Completed work is summarized in [Verified complete](#verified-complete-do-not-repeat) — do not repeat those unless you reset the environment.

---

## Remaining manual steps

### 1. New-customer onboarding test call

Call from a number **not** in `customers` (seed/import uses `+1555…`, `+15552001…`, `+19493313190`, `+19497771001–03`). Use your cell or another unlisted number.

- [ ] Onboarding flow audible on the call (`create_customer` path)
- [ ] After call end, new row in `customers`:

```bash
docker compose exec postgres psql -U hvac_user -d hvac_intel -c \
  "SELECT customer_id, full_name, phone_primary, created_at
   FROM customers
   WHERE phone_primary = '+1XXXXXXXXXX'
   ORDER BY created_at DESC;"
```

- [ ] Optional: customer detail page → **Call History** shows the onboarding call

---

### 2. ML feature pipeline (Kafka + Celery)

Postgres shows `feature_store = 0`. Uvicorn logs show `Kafka unavailable; dispatching Celery task directly` — Celery worker may not be running.

- [ ] Start pipeline services:
  ```bash
  docker compose up -d kafka celery-worker
  ```
  Or run Celery manually from `backend/` (see `docs/RUNBOOK.md`).
- [ ] Place a live call (or replay call-end webhook); confirm:
  - [ ] `process_call_features` runs in Celery logs
  - [ ] Row appears in `feature_store`
  - [ ] `churn_scores` updates (or `model_not_trained` if no `ml/artifacts/*.pkl`)

**Optional (when labeled data exists):**

- [ ] `python ml/training/train_churn_model.py` → deploy artifacts → restart backend + Celery
- [ ] Batch rescore smoke: `celery -A app.pipeline.celery_app call app.pipeline.tasks.batch_rescore_customers`

---

### 3. RAG live-call verification

Mock index exists (`data/knowledge/.mock_vector_index.json`). No `rag_knowledge_query` execution seen in recent uvicorn logs.

- [ ] On a live call, ask a FAQ/pricing question; confirm `rag_knowledge_query` in uvicorn logs with retrieved context

**Optional — real Pinecone (keys are set):**

- [ ] Index all namespaces: `faq_general`, `equipment_manuals`, `warranty_terms`, `troubleshooting`, `pricing`
- [ ] Add equipment manual PDFs under `data/knowledge/manuals/` before indexing manuals namespace

---

### 4. Dashboard SSE live feed (browser)

API auth works; SSE not manually verified in browser this session.

- [ ] Open `/dashboard` → **Live Activity Feed** shows connected (green)
- [ ] Trigger a call or batch rescore → event appears without refresh

---

### 5. Observability (Grafana)

Prometheus/Grafana not running in Docker (only postgres + redis up). `/metrics` returns 200.

- [ ] `docker compose up -d prometheus grafana`
- [ ] Build or import Grafana dashboard for: `vapi_webhook_total`, `tool_execution_latency_seconds`, `churn_scoring_latency_seconds`, `high_risk_accounts_total`, `saved_by_ai_total`, `rag_retrieval_latency_seconds`

---

### 6. Production deployment & pre-production gates

GitHub repo and CI are green. K8s and performance gates are not done.

- [ ] **Kubernetes (if deploying):** copy `infra/k8s/secrets.yaml.template` → `secrets.yaml`, set ingress hostname, `kubectl apply`
- [ ] **Secrets:** migrate from `.env` to AWS Secrets Manager / Vault for production
- [ ] **Pre-production gates** (`docs/PRE_PRODUCTION_CHECKLIST.md`): webhook p99, RAG p99, SSE 1h/50 conn, feature lag <30s, batch rescore SLA, Alembic on prod clone, churn AUC ≥ 0.78

---

### 7. Optional live tool exercises

All 12 tools are linked; exercise these on live calls when convenient:

- [ ] `create_customer` — covered by step 1 (new-customer onboarding call)
- [ ] `update_customer` — caller corrects address or phone mid-call
- [ ] `update_dispatch` — caller changes or cancels a booking
- [ ] `create_equipment` — register a unit for a new or existing customer
- [ ] `check_availability` / `lookup_service_info` — scheduling and pricing flows

---

## Verified complete (do not repeat)

Evidence sources noted in parentheses.

### Environment & infrastructure

| Item | Evidence |
|------|----------|
| Root `.env` created and populated | `.env` has all keys (Vapi, Pinecone, DB, API keys) |
| `frontend/.env.local` with matching API key | `NEXT_PUBLIC_API_KEY` = `DASHBOARD_API_KEY` |
| Postgres + Redis running | `docker compose ps` — both Up 24h+ |
| Alembic at head | `alembic_version`: `014_org_drive_folder` |
| DB seeded | 14 customers, 9 transcripts, 4 dispatch jobs, 6 churn scores |
| Health smoke | `curl localhost:8000/health` → 200 |
| Backend running | uvicorn terminal 26, `--reload` on :8000 |
| ngrok tunnel | terminal 23 → `stonework-congenial-booth.ngrok-free.dev` → :8000 |
| Frontend running | `npm run dev` terminal 27; `/dashboard` → 200 |

### Vapi dashboard & live-call plumbing

| Item | Evidence |
|------|----------|
| Assistant **HVAC Inbound Receptionist** | Vapi API; `VAPI_ASSISTANT_ID` in `.env` |
| Phone +19498800687 → assistant attached | Vapi phone-number API |
| Webhook URL → ngrok `/webhook/vapi` | Assistant + phone `server.url` |
| Dashboard `firstMessage` with `{{customer_name}}`, `{{equipment_info}}` | Vapi assistant config |
| System prompt with template variables + onboarding rules | Vapi `model.messages[0].content` |
| **All 12 tools linked to assistant** | Vapi API 2026-06-04: `toolIds` count = 12, account tools = 12, 0 unlinked — `check_availability`, `create_customer`, `create_equipment`, `create_support_ticket`, `get_customer_info`, `get_equipment_info`, `lookup_service_info`, `query_churn_score`, `rag_knowledge_query`, `schedule_dispatch`, `update_customer`, `update_dispatch` |
| Local HMAC bypass | `VAPI_WEBHOOK_HMAC_BYPASS=true`, `VAPI_WEBHOOK_SECRET=disabled` |

### Live calls & webhook (Phases 2, L, N, O partial)

| Item | Evidence |
|------|----------|
| Webhooks 200 OK, no 401 | ngrok + uvicorn logs 2026-06-03/04 |
| `end-of-call-report` handled | uvicorn: `Vapi event: end-of-call-report` |
| Transcripts persisted with enrichment | 4 live rows: `has_recording`, `has_summary`, `has_cost` = true |
| `get_customer_info` tool executed | uvicorn: `Executing Vapi tool … name=get_customer_info` |
| No `Unknown tool` errors | Recent logs clean |
| Dispatch jobs from live calls | 3× `AC_NO_COOLING` for Daniel V (2026-06-04) |
| Known-customer E2E (Daniel V +19493313190) | 4 live transcripts linked to customer `18ea568c…` |

### Auth (Phase 3)

| Item | Evidence |
|------|----------|
| `DASHBOARD_API_KEY` set | `.env` |
| Unauthenticated API → 401 | `GET /api/v1/customers` → 401 |
| Authenticated API → 200 | same with `X-API-Key` → 200 |

### Transcript API + Call History (Phase 2)

| Item | Evidence |
|------|----------|
| `GET …/customers/{id}/transcripts` | 4 items for Daniel V |
| `GET /api/v1/calls/{call_id}` | Returns transcript JSON for live call |

### RAG mock index (Phase 3 partial)

| Item | Evidence |
|------|----------|
| Mock FAQ index built | `data/knowledge/.mock_vector_index.json` exists (~49k lines) |

### Tests & CI (Phases 7–8 partial)

| Item | Evidence |
|------|----------|
| pytest suite | **145 passed** (2026-06-04) |
| GitHub repo + CI green | `dverc/hvac-intelligence`; latest CI + Deploy success |
| App metrics endpoint | `GET /metrics` → 200 |

### Analytics API (Phase 5 partial)

| Item | Evidence |
|------|----------|
| `GET /api/v1/analytics/churn-distribution` | 200 with API key |

---

## Quick reference

| Doc | Purpose |
|-----|---------|
| `docs/vapi_tool_schemas.md` | JSON for 4 new Vapi tools |
| `docs/RUNBOOK.md` | Celery, Kafka, indexing, batch rescore |
| `docs/PRE_PRODUCTION_CHECKLIST.md` | Production gate criteria |
| `HVAC_Intelligence_Project_Aero_TechSpec.md` | Full spec (Phases 0–8) |
