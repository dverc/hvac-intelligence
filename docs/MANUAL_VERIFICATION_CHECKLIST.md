# Manual Verification Checklist (Outside Cursor)

Last audited: **2026-06-11** (ground truth in [`docs/CURSOR_PROJECT_NOTES.md`](./CURSOR_PROJECT_NOTES.md)).

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

- [ ] Confirm six containers Up: `postgres`, `redis`, `kafka`, `zookeeper`, `celery-worker`, `celery-beat` (`docker compose ps`)
- [ ] **Celery queue fix:** worker must use `-Q celery,features,scoring` or beat tasks (Jobber sync, batch rescore, outbound launcher) never run — see `docs/CURSOR_PROJECT_NOTES.md`
- [ ] Place a live call (or replay call-end webhook); confirm:
  - [ ] `process_call_features` runs in Celery logs
  - [ ] Row appears in `feature_store`
  - [ ] `churn_scores` updates (or `model_not_trained` if no `ml/artifacts/*.pkl`)

**Optional (when labeled data exists):**

- [ ] `python ml/training/train_churn_model.py` → deploy artifacts → restart backend + Celery
- [ ] Batch rescore smoke: `celery -A app.pipeline.celery_app call app.pipeline.tasks.batch_rescore_customers`

---

### 3. RAG live-call verification

Mock index exists (`data/knowledge/.mock_vector_index.json`).

- [ ] On a live call, ask a FAQ/pricing question; confirm `rag_knowledge_query` in uvicorn logs with retrieved context

**Optional — real Pinecone (keys are set):**

- [ ] Index all namespaces: `faq_general`, `equipment_manuals`, `warranty_terms`, `troubleshooting`, `pricing`
- [ ] Add equipment manual PDFs under `data/knowledge/manuals/` before indexing manuals namespace

---

### 4. Dashboard SSE live feed (browser)

- [ ] Open `/dashboard` → **Live Activity Feed** shows connected (green)
- [ ] Trigger a call or batch rescore → event appears without refresh

---

### 5. Portal timezone (frontend bug)

- [ ] Backend returns appointment times in org timezone (`OrgSettings`) ✅
- [ ] **Frontend still hardcodes `America/Los_Angeles`** in `frontend/lib/portal-format.ts` ❌ — verify display for non-Pacific org after fix

---

### 6. Pending Vapi dashboard tools

12 tools linked in Vapi. Two more exist in code but **not yet added to Vapi dashboard**:

- [ ] `transfer_call`
- [ ] `check_service_area`

Schemas: `docs/vapi_tool_schemas.md`

---

### 7. Timezone booking test (pending)

- [ ] Make a test call booking **Marcus at 2–4 PM**; verify Google Calendar shows correct **PDT** (not 8 AM default)

---

### 8. Observability (Grafana)

- [ ] `docker compose up -d prometheus grafana`
- [ ] Build or import Grafana dashboard for: `vapi_webhook_total`, `tool_execution_latency_seconds`, `churn_scoring_latency_seconds`, `high_risk_accounts_total`, `saved_by_ai_total`, `rag_retrieval_latency_seconds`

---

### 9. Production deployment & pre-production gates

- [ ] **Kubernetes (if deploying):** copy `infra/k8s/secrets.yaml.template` → `secrets.yaml`, set ingress hostname, `kubectl apply`
- [ ] **Secrets:** migrate from `.env` to AWS Secrets Manager / Vault for production
- [ ] **Pre-production gates** (`docs/PRE_PRODUCTION_CHECKLIST.md`): webhook p99, RAG p99, SSE 1h/50 conn, feature lag <30s, batch rescore SLA, Alembic on prod clone, churn AUC ≥ 0.78

---

### 10. Optional live tool exercises

All **12 Vapi-linked** tools; exercise on live calls when convenient:

- [ ] `create_customer` — covered by step 1
- [ ] `update_customer` — caller corrects address or phone mid-call
- [ ] `update_dispatch` — caller changes or cancels a booking
- [ ] `create_equipment` — register a unit for a new or existing customer
- [ ] `check_availability` / `lookup_service_info` — scheduling and pricing flows

---

## Verified complete (do not repeat)

Evidence sources noted in parentheses.

### Environment & infrastructure (2026-06-11)

| Item | Evidence |
|------|----------|
| Root `.env` created and populated | `.env` has all keys (Vapi, Pinecone, DB, API keys) |
| `frontend/.env.local` with matching API key | `NEXT_PUBLIC_API_KEY` = `DASHBOARD_API_KEY` |
| **Six containers Up** | `docker compose ps`: postgres (`pgvector/pgvector:pg16`), redis, kafka, zookeeper, celery-worker, celery-beat |
| Alembic at head | `029_org_settings_constraints` |
| Daniel V seed customer | `customer_id` `18ea568c-5db5-4a41-ab1d-18314a9d54e4`, phone `+19493313190` |
| Two orgs in DB | Demo `00000000-…0001`; **Bob** `bff79a29-…` (not "Bob's Plumbing") |
| Admin login user | `daniel@hvacintelligence.com`, `users.id` `0b5a31f1-…`, role admin (register API, not migration) |
| Health smoke | `curl localhost:8000/health` → 200 |
| Dashboard | `/dashboard/health` (not `/system-health`) |

### Vapi dashboard & live-call plumbing

| Item | Evidence |
|------|----------|
| Assistant **HVAC Inbound Receptionist** | Vapi API; `VAPI_ASSISTANT_ID` in `.env` |
| Phone +19498800687 → assistant attached | Vapi phone-number API |
| Webhook URL → ngrok `/webhook/vapi` | Assistant + phone `server.url` |
| **12 tools linked in Vapi** | `check_availability`, `create_customer`, `create_equipment`, `create_support_ticket`, `get_customer_info`, `get_equipment_info`, `lookup_service_info`, `query_churn_score`, `rag_knowledge_query`, `schedule_dispatch`, `update_customer`, `update_dispatch` |
| `transfer_call` / `check_service_area` | In `tool_executor.py`; **pending Vapi setup** |

### Live calls & webhook

| Item | Evidence |
|------|----------|
| Last fully successful documented call | **2026-06-03**, cost **$0.58** |
| Stalled / failed follow-ups | `019e911d-4d3d` ($0.1232, phone without +1); `019e911e-9355` ($0.0018, hangup) |
| Dashboard total calls | **21** (cumulative test calls) |
| Known-customer E2E (Daniel V) | Transcripts linked to `18ea568c…` |
| Dispatch jobs from live calls | Multiple `AC_NO_COOLING` for Daniel V |

### Auth

| Item | Evidence |
|------|----------|
| `DASHBOARD_API_KEY` + JWT on dashboard routes | `X-API-Key` + `Authorization: Bearer` |
| `JWT_SECRET_KEY` in `.env` / CI | Not `SECRET_KEY` |
| Admin role check | `role == "admin"` only; no `is_superuser` |

### Onboarding UIs

| Item | Evidence |
|------|----------|
| Self-service 6-step wizard | `/dashboard/onboarding` loads |
| Admin 5-step wizard | `/dashboard/admin/onboarding/[org_id]` |

### Tests & CI

| Item | Evidence |
|------|----------|
| pytest suite | **320 passed** (2026-06-11) |
| GitHub repo + CI green | `dverc/hvac-intelligence` |

---

## Quick reference

| Doc | Purpose |
|-----|---------|
| `docs/CURSOR_PROJECT_NOTES.md` | **Ground truth** for agents (DB, APIs, bugs) |
| `docs/vapi_tool_schemas.md` | JSON for Vapi tools (incl. pending) |
| `docs/RUNBOOK.md` | Celery, Kafka, indexing, batch rescore |
| `docs/PRE_PRODUCTION_CHECKLIST.md` | Production gate criteria |
| `HVAC_Intelligence_Project_Aero_TechSpec.md` | Full spec (Phases 0–8) |
