# Manual Verification Checklist (Outside Cursor)

Complete these steps **after all coding phases are submitted**. Check items off as you go.

---

## Priority — Register new Vapi tools + new-customer onboarding call

Do these in order (Enhancement Phase 4).

### 1. Add the 4 new tools in Vapi dashboard

The agent **cannot** call these until they are registered in Vapi.

- [ ] Open [Vapi dashboard](https://dashboard.vapi.ai) → your assistant (**HVAC Inbound Receptionist**) → **Tools** → **Add** (Function) for each tool below
- [ ] Copy the JSON for each tool from [`docs/vapi_tool_schemas.md`](vapi_tool_schemas.md):
  - [ ] `create_customer`
  - [ ] `update_customer`
  - [ ] `create_equipment`
  - [ ] `update_dispatch`
- [ ] Restart backend/uvicorn after saving (so the tool handlers are loaded)

### 2. Test call as a new customer (unknown phone number)

- [ ] Call your Vapi inbound number from a phone **not** in the database  
  (seed data uses `+1555…` and `+15552001…` ranges — use your real cell or any number you have not seeded)
- [ ] During the call, confirm the **onboarding flow** kicks in (agent treats you as unknown, collects info, uses `create_customer`)
- [ ] After the call ends, confirm a **new row** in `customers`

**Run this to verify** (replace `+1XXXXXXXXXX` with the number you called from):

```bash
docker compose exec postgres psql -U hvac_user -d hvac_intel -c \
  "SELECT customer_id, full_name, phone_primary, account_status, created_at
   FROM customers
   WHERE phone_primary = '+1XXXXXXXXXX'
   ORDER BY created_at DESC;"
```

Or list the most recently created customers:

```bash
docker compose exec postgres psql -U hvac_user -d hvac_intel -c \
  "SELECT customer_id, full_name, phone_primary, created_at
   FROM customers
   ORDER BY created_at DESC
   LIMIT 5;"
```

- [ ] New customer row exists with the caller's phone and name from the call
- [ ] Optional: open that customer in the dashboard → **Call History** shows the onboarding call

---

This covers:
- **Tech Spec Phases 0–8** (original build in `HVAC_Intelligence_Project_Aero_TechSpec.md`)
- **Enhancement Phases 1–4** (transcript persistence, Call History UI, auth, new voice tools)

---

## Part A — One-time local environment setup

Do this once before any phase verification.

- [ ] **Copy env templates**
  - `cp .env.example .env` (project root)
  - `cp frontend/.env.example frontend/.env.local`
- [ ] **Generate dashboard API key** (must match frontend ↔ backend):
  ```bash
  openssl rand -hex 32
  ```
  - Set `DASHBOARD_API_KEY=` in root `.env`
  - Set `NEXT_PUBLIC_API_KEY=` to the **same value** in `frontend/.env.local`
- [ ] **Fill remaining `.env` values** (see `.env.example` comments):
  - `POSTGRES_PASSWORD`, `DATABASE_URL`
  - `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
  - `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`, `VAPI_WEBHOOK_SECRET`
  - `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`, `PINECONE_INDEX_NAME`
  - `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS`
- [ ] **Start infrastructure**
  ```bash
  docker compose up -d postgres redis
  ```
- [ ] **Migrate and seed**
  ```bash
  cd backend && alembic upgrade head && cd ..
  python scripts/seed_database.py
  ```
- [ ] **Smoke check**
  ```bash
  curl -sf http://localhost:8000/health
  ```

---

## Part B — Vapi dashboard & live-call plumbing (do once, re-verify after tool changes)

These are **manual steps in the [Vapi dashboard](https://dashboard.vapi.ai)** and your terminal — not in Cursor.

### B.1 Assistant & phone number

- [ ] Create or confirm assistant **"HVAC Inbound Receptionist"**; copy ID → `VAPI_ASSISTANT_ID` in `.env`
- [ ] Attach that assistant to your inbound **phone number** (fixed-assistant pattern — Vapi sends `call-started`, not `assistant-request`)
- [ ] Set assistant **Server URL** (webhook) to your public backend:
  - **Local dev:** run ngrok (or similar) and point at `https://<your-tunnel>/webhook/vapi`
  - **Production:** `https://<your-domain>/webhook/vapi`
- [ ] Set assistant **first message** in the dashboard (not via webhook):
  ```
  Hi {{customer_name}}, thank you for calling. I see your {{equipment_info}} on file. How can I help you today?
  ```
- [ ] Set assistant **system prompt** to use template variables injected by the webhook:
  - `{{call_id}}`, `{{customer_name}}`, `{{customer_id}}`, `{{account_status}}`
  - `{{equipment_info}}`, `{{open_tickets}}`, `{{churn_risk}}`, `{{retention_protocol}}`
  - Ensure the prompt tells the model to follow injected context and use tools

### B.2 Tool definitions (Assistant → Tools → Function)

**Original six tools** (tech spec §4.2 — should already exist):

- [ ] `get_customer_info`
- [ ] `get_equipment_info`
- [ ] `schedule_dispatch`
- [ ] `query_churn_score`
- [ ] `rag_knowledge_query`
- [ ] `create_support_ticket`

**Four new tools** (Enhancement Phase 4 — **required before live onboarding works**):

Go to assistant → **Tools** → add each Function using JSON from `docs/vapi_tool_schemas.md`. The agent cannot invoke them until registered here.

- [ ] `create_customer`
- [ ] `update_customer`
- [ ] `create_equipment`
- [ ] `update_dispatch`

Each tool's server URL must reach your backend webhook (Vapi routes tool calls to `/webhook/vapi`).

### B.3 Webhook security (local vs production)

- [ ] **Local dev:** `VAPI_WEBHOOK_HMAC_BYPASS=true` and/or `VAPI_WEBHOOK_SECRET=disabled` in `.env` (never use in production)
- [ ] **Production:** set a real `VAPI_WEBHOOK_SECRET` in Vapi dashboard **and** `.env`; set `VAPI_WEBHOOK_HMAC_BYPASS=false`; remove `disabled` bypass

### B.4 After any backend or tool change

- [ ] Restart backend so it picks up code + env:
  ```bash
  # if using compose
  docker compose restart backend
  # or if running uvicorn directly
  cd backend && uvicorn app.main:app --reload
  ```

---

## Part C — Tech Spec Phase 0: Scaffold & environment

- [ ] Confirm `docker compose up --build` starts without errors (postgres, redis, kafka, backend, celery-worker, frontend)
- [ ] Confirm `curl http://localhost:8000/health` returns 200
- [ ] Confirm frontend loads at http://localhost:3000

---

## Part D — Tech Spec Phase 1: Database layer

- [ ] Run `alembic upgrade head` on a fresh Postgres — no migration errors
- [ ] Run `python scripts/seed_database.py` — 10 customers, 2 technicians, 5 transcripts seeded
- [ ] Optional: inspect tables in psql/pgAdmin (`customers`, `call_transcripts`, `churn_scores`, etc.)

---

## Part E — Tech Spec Phase 2: Vapi webhook & tool execution

- [ ] Start backend; expose via ngrok if testing live calls
- [ ] **Postman smoke:** `POST /webhook/vapi` with a signed or bypassed payload (see `backend/tests/conftest.py` `sign_vapi_payload`)
- [ ] **Live call:** place a test call; confirm in uvicorn logs:
  - [ ] `call-started` (or `call-start`) event — no 401
  - [ ] `tool-calls` events when the agent uses tools — no `Unknown tool`
  - [ ] Customer context logged (name, churn tier)
- [ ] Ask the agent to schedule dispatch — confirm a row appears in `dispatch_jobs`

---

## Part F — Tech Spec Phase 3: RAG pipeline

- [ ] **Mock index (local, no Pinecone bill):**
  ```bash
  python scripts/index_knowledge_base.py \
    --namespace faq_general \
    --source data/knowledge/faqs/ \
    --mock
  ```
- [ ] **Optional — real Pinecone:**
  - [ ] Create Pinecone index `hvac-knowledge` (dim 1536, cosine)
  - [ ] Index all namespaces: `faq_general`, `equipment_manuals`, `warranty_terms`, `troubleshooting`, `pricing`
  - [ ] Drop PDFs into `data/knowledge/manuals/` before indexing manuals namespace
- [ ] **Live call test:** ask a FAQ question; confirm `rag_knowledge_query` returns context in uvicorn logs

---

## Part G — Tech Spec Phase 4: ML feature pipeline (Kafka + Celery)

- [ ] Start full stack:
  ```bash
  docker compose up -d kafka celery-worker
  ```
  Or manually:
  ```bash
  celery -A app.pipeline.celery_app worker -Q features,scoring -c 4 --loglevel=info
  ```
- [ ] **After a live call ends**, confirm in logs/DB:
  - [ ] Celery task `process_call_features` runs
  - [ ] Row in `feature_store` for the customer
  - [ ] New or updated row in `churn_scores` (or `model_not_trained` if no artifacts yet)
- [ ] **Optional — train churn model** (when labeled data exists):
  ```bash
  python ml/training/train_churn_model.py
  ```
  Then restart backend + celery-worker to load `ml/artifacts/*.pkl`
- [ ] **Manual batch rescore smoke:**
  ```bash
  cd backend
  celery -A app.pipeline.celery_app call app.pipeline.tasks.batch_rescore_customers
  ```

---

## Part H — Tech Spec Phase 5: Analytics API & SSE

- [ ] Open dashboard Overview — **Live Activity Feed** connects (SSE indicator green)
- [ ] Trigger a call or batch rescore — event appears in the feed without page refresh
- [ ] Confirm API endpoints respond (with `X-API-Key` header):
  - `GET /api/v1/analytics/churn-distribution`
  - `GET /api/v1/analytics/saved-by-ai`
  - `GET /api/v1/stream/churn-events`

---

## Part I — Tech Spec Phase 6: Next.js frontend dashboard

- [ ] `cd frontend && npm install && npm run dev`
- [ ] Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `frontend/.env.local`
- [ ] Set `NEXT_PUBLIC_API_KEY` (same as `DASHBOARD_API_KEY`)
- [ ] Browse and confirm pages load with data:
  - [ ] `/dashboard` — KPI donut, live feed, Saved by AI metrics
  - [ ] `/dashboard/customers` — search and pagination
  - [ ] `/dashboard/customers/[id]` — churn timeline
  - [ ] `/dashboard/analytics` — cohort / retention views

---

## Part J — Tech Spec Phase 7: Testing & observability

- [ ] Run test suite locally:
  ```bash
  cd backend && pytest tests/ -v --cov=app --cov-report=term-missing
  ```
- [ ] Start Prometheus + Grafana:
  ```bash
  docker compose up -d prometheus grafana
  ```
  - Prometheus: http://localhost:9090
  - Grafana: http://localhost:3001 (admin / `GRAFANA_PASSWORD` from `.env`)
- [ ] **Build or import Grafana dashboard** covering:
  - `vapi_webhook_total`
  - `tool_execution_latency_seconds`
  - `churn_scoring_latency_seconds`
  - `high_risk_accounts_total`
  - `saved_by_ai_total`
  - `rag_retrieval_latency_seconds`
- [ ] Confirm app metrics scrape: http://localhost:8000/metrics

---

## Part K — Tech Spec Phase 8: Production deployment

- [ ] **GitHub:** create public repo `hvac-intelligence`, push local code, confirm CI workflow green
- [ ] **Kubernetes (if deploying):**
  - [ ] Copy `infra/k8s/secrets.yaml.template` → `secrets.yaml`; replace all `REPLACE_ME`
  - [ ] Set production hostname in `infra/k8s/ingress.yaml`
  - [ ] `kubectl apply -f infra/k8s/namespace.yaml` then remaining manifests
  - [ ] Set GitHub secret `KUBECONFIG` for deploy workflow
- [ ] **Secrets:** migrate from `.env` to AWS Secrets Manager / Vault (no `.env` in prod)
- [ ] **Pre-production gates** (`docs/PRE_PRODUCTION_CHECKLIST.md`):
  - [ ] Webhook p99 < 200 ms (Prometheus or load test)
  - [ ] RAG p99 < 800 ms
  - [ ] SSE stable 1 h+ with 50 concurrent connections
  - [ ] Feature pipeline lag < 30 s after call end
  - [ ] Batch rescore SLA on 500-account corpus
  - [ ] Alembic idempotent on prod schema clone
  - [ ] Churn model AUC-ROC ≥ 0.78 (when trained)

---

## Part L — Enhancement Phase 1: Transcript persistence fix

- [ ] Restart backend after deploy
- [ ] Place a **live test call**
- [ ] Confirm uvicorn logs show `end-of-call-report` (not just `call-end`)
- [ ] Confirm persistence summary logged after call end
- [ ] Confirm row in `call_transcripts` with enrichment fields (recording URL, summary, cost, etc.)

---

## Part M — Enhancement Phase 2: Transcript API + Call History UI

- [ ] With backend + frontend running and API key configured:
  - [ ] `GET /api/v1/customers/{id}/transcripts` returns full transcript list (via curl/Postman with `X-API-Key`)
  - [ ] `GET /api/v1/calls/{call_id}` returns transcript detail
- [ ] In browser: open a customer detail page → **Call History** tab
  - [ ] Past calls listed with date, duration, outcome
  - [ ] Expand a call — transcript text visible
  - [ ] Recording player works if Vapi provided a recording URL

---

## Part N — Enhancement Phase 3: Authentication + HMAC hardening

- [ ] Confirm `DASHBOARD_API_KEY` set in root `.env`
- [ ] Confirm `NEXT_PUBLIC_API_KEY` matches in `frontend/.env.local`
- [ ] Restart frontend (`npm run dev`) after env change
- [ ] Dashboard loads without "API key not configured" error
- [ ] Confirm unauthenticated API calls return 401:
  ```bash
  curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/customers
  # expect 401
  ```
- [ ] **Pre–Enhancement Phase 4 live call** (auth regression check):
  - [ ] Webhook events in uvicorn logs (no 401 — webhook uses HMAC/bypass, not API key)
  - [ ] Transcript persisted on call end
  - [ ] Call visible on customer detail **Call History** tab

---

## Part O — Enhancement Phase 4: New voice tools (create/update customer, equipment, dispatch)

See **Priority** section at the top for the two-step flow (register tools → new-customer test call + SQL verify).

- [ ] Add the **4 new tool definitions** in Vapi dashboard (see Part B.2 and `docs/vapi_tool_schemas.md`) — agent cannot call them until registered
- [ ] **Restart uvicorn/backend** so tool registry picks up handlers
- [ ] **Live E2E call — known customer** (e.g. seeded phone `+19493313190`):
  - [ ] Webhook events in logs — no 401, no unknown-tool errors
  - [ ] Agent speaks personalized greeting using `{{customer_name}}` / `{{equipment_info}}`
  - [ ] Transcript persisted on call end
  - [ ] Call visible on customer detail **Call History** tab
- [ ] **Live E2E call — unknown caller / new customer** (number **not** in `customers` — see Priority section):
  - [ ] Onboarding flow audible on the call (`create_customer` path)
  - [ ] `SELECT … FROM customers WHERE phone_primary = '<your test number>'` returns a new row (or appears in `ORDER BY created_at DESC LIMIT 5`)
  - [ ] Transcript + Call History reflect the new account
- [ ] **Optional tool exercises on a live call:**
  - [ ] `update_customer` — caller corrects address or phone
  - [ ] `update_dispatch` — caller changes or cancels a booking

---

## Part P — Final end-to-end demo checklist

Run this once everything above passes.

- [ ] `docker compose up --build` (or backend + frontend + celery + kafka individually)
- [ ] Dashboard at http://localhost:3000 — all pages load with auth
- [ ] Live inbound call → tools execute → transcript saved → Call History updated
- [ ] Churn score updates in Celery logs / customer detail (or `model_not_trained` acknowledged)
- [ ] SSE live feed shows call activity
- [ ] Grafana dashboards show webhook and scoring metrics
- [ ] CI green on GitHub

---

## Quick reference

| Doc | Purpose |
|-----|---------|
| `docs/vapi_tool_schemas.md` | JSON for 4 new Vapi tools |
| `docs/RUNBOOK.md` | Celery, Kafka, indexing, batch rescore |
| `docs/PRE_PRODUCTION_CHECKLIST.md` | Production gate criteria |
| `HVAC_Intelligence_Project_Aero_TechSpec.md` | Full spec (Phases 0–8) |
