# HVAC-Intelligence (Project Aero)

**Real-time inbound voice agent + ML churn engine for HVAC service operations.**

[![CI](https://github.com/dverc/hvac-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/dverc/hvac-intelligence/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![Next.js 14](https://img.shields.io/badge/Next.js-14-black)

Full technical specification: [`HVAC_Intelligence_Project_Aero_TechSpec.md`](./HVAC_Intelligence_Project_Aero_TechSpec.md)

---

## What this is

Project Aero is a production-shaped HVAC operations platform that couples a low-latency inbound voice agent with a predictive churn engine at the data layer. Inbound calls hit Vapi (Deepgram ASR + Claude tool-calling); the FastAPI backend handles webhooks, dispatches six deterministic tools (dispatch, churn lookup, RAG, tickets, equipment, customer profile), and streams every completed call into a feature pipeline. Transcripts, sentiment trajectories, and speech markers become rolling-window feature vectors in PostgreSQL; a gradient-boosted ensemble (XGBoost + LightGBM) scores 90-day churn probability on a configurable cadence.

The voice path never blocks on ML inference. Call-end events publish to Kafka (`call.features`); Celery workers extract features, upsert `feature_store`, and write `churn_scores` asynchronously. A Next.js dashboard consumes REST analytics and an SSE churn-event stream so operators see risk movement, cohorts, and retention outcomes in near real time.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INBOUND CALL INGESTION                             │
│                                                                             │
│   [PSTN/SIP Caller] ──▶ [Vapi Voice Platform] ──▶ [WebSocket Audio Stream] │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │  Real-time audio (16kHz PCM)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VAPI ORCHESTRATION LAYER                            │
│                                                                             │
│  ┌──────────────┐    ┌───────────────────┐    ┌──────────────────────────┐ │
│  │ Vapi Speech  │    │  Claude Reasoning  │    │    Vapi Tool Router      │ │
│  │ Recognition  │───▶│  Engine (claude-   │───▶│  (tool_call dispatcher)  │ │
│  │ (Deepgram)   │    │  sonnet-4-20250514)│    │                          │ │
│  └──────────────┘    └────────┬──────────┘    └──────────┬───────────────┘ │
└───────────────────────────────┼────────────────────────────┼────────────────┘
                                │ LLM reasoning              │ Tool calls
                                ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND (Python 3.11+)                      │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐   │
│  │ /webhook/vapi   │  │  RAG Pipeline   │  │  Tool Execution Layer    │   │
│  │ (event handler) │  │  (LangChain +   │  │  - schedule_dispatch()   │   │
│  │                 │  │   Pinecone)     │  │  - query_churn_score()   │   │
│  │  - call.started │  │                 │  │  - update_customer()     │   │
│  │  - transcript   │  │  Vector Search  │  │  - create_ticket()       │   │
│  │  - call.ended   │  │  (cosine sim.)  │  │  - get_equipment_info()  │   │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬───────────────┘   │
│           │                    │                        │                    │
│           ▼                    ▼                        ▼                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     SERVICE LAYER (Dependency Injected)              │   │
│  │  CustomerService │ DispatchService │ ChurnService │ TranscriptService│   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
└──────────────────────────────────┼─────────────────────────────────────────┘
                                   │
              ┌────────────────────┼──────────────────────┐
              ▼                    ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
│   PostgreSQL 16     │  │   Pinecone (Vector)  │  │   Apache Kafka       │
│                     │  │                      │  │                      │
│  - customers        │  │  - faq_embeddings    │  │  Topics:             │
│  - call_transcripts │  │  - equipment_manuals │  │  - call.features     │
│  - technicians      │  │  - service_history   │  │  - churn.scores      │
│  - dispatch_jobs    │  │                      │  │  - alerts.high_risk  │
│  - churn_scores     │  │  dim: 1536           │  │                      │
│  - feature_store    │  │  metric: cosine      │  │  Retention: 30 days  │
└─────────────────────┘  └─────────────────────┘  └──────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ML FEATURE PIPELINE (Celery + Redis)                │
│                                                                             │
│  KafkaConsumer → FeatureExtractor → FeatureStore → ChurnModelInference     │
│                                                                             │
│  Models: XGBoost (primary) + LightGBM (ensemble) + Isolation Forest        │
│  Scoring cadence: 6-hour rolling window (configurable)                      │
│  Output: churn_probability [0.0–1.0], risk_tier [LOW/MED/HIGH/CRITICAL]    │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NEXT.JS 14 DASHBOARD (App Router)                   │
│                                                                             │
│  Tremor UI Components │ Recharts Visualizations │ Server-Sent Events (SSE) │
│                                                                             │
│  - /dashboard          - ChurnRiskHeatmap         - Live call feed          │
│  - /customers/:id      - RetentionTimeSeries       - Risk score updates      │
│  - /analytics          - CohortRiskTable           - Dispatch notifications  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Voice AI | Vapi (Deepgram ASR, PSTN/SIP ingress) |
| LLM Reasoning | Anthropic Claude (tool-calling via Vapi) |
| Backend | FastAPI 0.11x, Python 3.11, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 + pgvector |
| Vector DB | Pinecone (local JSON mock index for dev) |
| Message Broker | Apache Kafka |
| Task Queue | Celery + Redis |
| ML Models | XGBoost, LightGBM, Isolation Forest; DistilBERT sentiment; SHAP explanations |
| Frontend | Next.js 14, Tremor, Recharts, Tailwind |
| Observability | Prometheus, Grafana, custom app metrics on `/metrics` |

---

## Quick start

1. **Clone** and enter the repo.
2. **Configure env:** `cp .env.example .env`

   **Required to boot the API locally** (non-empty strings; test placeholders are fine):

   | Variable | Purpose |
   |----------|---------|
   | `POSTGRES_PASSWORD` | Matches `docker-compose` Postgres |
   | `DATABASE_URL` | Async SQLAlchemy URL (see `.env.example`) |
   | `ANTHROPIC_API_KEY` | Settings validation (voice uses Vapi in production) |
   | `OPENAI_API_KEY` | Settings validation |
   | `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, `VAPI_ASSISTANT_ID` | Webhook HMAC + Vapi integration |
   | `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT` | Settings validation |
   | `REDIS_URL` | Celery broker |
   | `KAFKA_BOOTSTRAP_SERVERS` | Feature pipeline (dev falls back to direct Celery if broker is down) |

   **Optional for full functionality:**

   | Variable | When you need it |
   |----------|------------------|
   | Real `OPENAI_API_KEY` + `PINECONE_API_KEY` | Live Pinecone RAG (omit `--mock` on indexer) |
   | `VAPI_*` with real values | Live phone / Postman webhooks against production assistant |
   | Kafka + `celery-worker` in compose | End-to-end `call.features` → scoring without dev fallback |
   | `ml/artifacts/*.pkl` | Non–`model_not_trained` churn scores |

3. **Start data services:** `docker compose up -d postgres redis`
4. **Migrate:** `cd backend && alembic upgrade head`
5. **Seed:** `python scripts/seed_database.py` (from repo root)
6. **Index FAQs (mock):** `python scripts/index_knowledge_base.py --namespace faq_general --source data/knowledge/faqs/ --mock`
7. **API:** `cd backend && uvicorn app.main:app --reload`
8. **Dashboard:** `cd frontend && npm install && npm run dev`

**Dashboard at http://localhost:3000 · API docs at http://localhost:8000/docs**

For the full stack (Kafka, Celery, Prometheus, Grafana): `docker compose up --build`. See [`docs/RUNBOOK.md`](./docs/RUNBOOK.md).

---

## Project structure

```
.
├── backend/          # FastAPI app, Alembic migrations, pytest suite
│   ├── alembic/
│   ├── app/
│   └── tests/
├── frontend/         # Next.js 14 dashboard (App Router)
│   ├── app/
│   ├── components/
│   └── lib/
├── ml/               # Training scripts and scored model artifacts
│   ├── artifacts/
│   └── training/
├── infra/            # Prometheus config, Kubernetes manifests
│   └── k8s/
├── scripts/          # Database seed and knowledge-base indexer
├── data/             # FAQ sources and mock vector index output
├── docs/             # Runbook, pre-production checklist
├── .github/          # CI (pytest + build) and deploy workflows
└── docker-compose.yml
```

---

## Key engineering decisions

- **Kafka before Celery for call-end features** — Decouples webhook ACK latency from feature extraction; consumers scale independently and replay topics after outages.
- **Voice agent never awaits ML inference** — `call.ended` returns after persistence + publish; scoring runs in workers so p99 webhook latency stays bounded.
- **Lexicon-based `classify_emotions()` instead of a second transformer** — Deterministic, fast, and testable on every utterance; DistilBERT handles document-level sentiment only.
- **PostgreSQL views for `age_years` / `tenure_years` (Option C)** — Generated columns cannot call `NOW()` in PostgreSQL; views compute ages at read time without stale stored values.
- **Mock vector store when Pinecone/OpenAI keys are absent** — Local and CI runs exercise RAG tool paths without paid API dependencies.
- **HMAC-verified Vapi webhooks** — Same signing contract in tests (`sign_vapi_payload`) and production middleware; rejects forged call-end events.
- **SSE + Redis pub/sub for dashboard updates** — Push churn and call events to browsers without polling; nginx ingress timeouts extended for long-lived streams.
- **Graceful `model_not_trained` in churn ensemble** — Feature pipeline and API stay operational before labeled data and `ml/artifacts/` exist; training is an operational step, not a boot blocker.

---

## Running tests

From `backend/` (Postgres with pgvector required; see `backend/tests/conftest.py`):

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

Coverage gate: **60%** (see `backend/.coveragerc` for omitted infrastructure entrypoints). CI runs the same suite on every push — [`.github/workflows/ci.yml`](./.github/workflows/ci.yml).

---

## Roadmap

1. **Train the churn model** — Run `ml/training/train_churn_model.py` once `feature_store` has labeled rows; deploy artifacts to `ml/artifacts/`.
2. **Live Vapi demo** — Point a phone number at `POST /webhook/vapi` with production secrets; validate call-start context injection and call-end scoring in Celery logs.
3. **Technician churn on the dashboard** — Extend scoring and UI beyond `entity_type=CUSTOMER` to technician retention signals.

---

## Documentation

| Doc | Description |
|-----|-------------|
| [`HVAC_Intelligence_Project_Aero_TechSpec.md`](./HVAC_Intelligence_Project_Aero_TechSpec.md) | Full system spec (schemas, APIs, phases) |
| [`docs/RUNBOOK.md`](./docs/RUNBOOK.md) | Operations: Celery, Kafka, batch rescore, observability |
| [`docs/PRE_PRODUCTION_CHECKLIST.md`](./docs/PRE_PRODUCTION_CHECKLIST.md) | Production gate criteria |
