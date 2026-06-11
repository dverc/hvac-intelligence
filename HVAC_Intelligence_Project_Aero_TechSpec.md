# HVAC-Intelligence (Project Aero)
## Technical Specification & Cursor Implementation Guide
**Version:** 1.0.0 | **Status:** Implementation-Ready | **Classification:** Internal Engineering

> **Operational ground truth (2026-06-11):** For current DB state, API paths (`/api/v1/scheduling/*`), auth (`JWT_SECRET_KEY`, dual JWT + API key), Celery queue bug, Vapi tool status, and verified org/user IDs, see [`docs/CURSOR_PROJECT_NOTES.md`](docs/CURSOR_PROJECT_NOTES.md). This spec may lag behind live ops notes.

---

## Table of Contents

1. [Executive Summary & Business ROI](#1-executive-summary--business-roi)
2. [System Architecture & Data Flow](#2-system-architecture--data-flow)
3. [Database Schemas & Feature Store](#3-database-schemas--feature-store)
4. [API Contracts & Tool Calling](#4-api-contracts--tool-calling)
5. [Visualization Specifications](#5-visualization-specifications)
6. [Cursor Implementation Plan](#6-cursor-implementation-plan)

---

## 1. Executive Summary & Business ROI

### Technical Complexity Statement

Project Aero is a production-grade, AI-native HVAC operations platform that fuses real-time inbound voice intelligence with a machine-learning-driven predictive churn engine — two systems that are architecturally coupled at the data layer. System 1 deploys a low-latency streaming voice agent (Vapi + Claude) that performs real-time intent classification, entity extraction, and dispatching via deterministic tool-calling within a stochastic LLM inference loop. Critically, every call interaction is simultaneously processed by an event-driven feature pipeline that transforms raw audio transcripts, sentiment trajectories, and speech hesitation markers into high-dimensional feature vectors persisted in a time-series feature store. These vectors serve as primary inputs to System 2: a gradient-boosted ensemble model (XGBoost + LightGBM) that produces 90-day churn probability scores for both customer accounts and HVAC technician employees. The architecture enforces strict separation of concerns — the voice agent never blocks on ML inference; instead, features are emitted asynchronously via Kafka topics, consumed by the feature pipeline, and scored by the churn model on a configurable cadence (default: 6-hour rolling windows). System 3 closes the loop with a Next.js/Tremor/Recharts dashboard that visualizes real-time churn signal degradation, cohort risk stratification, and AI-attributable retention events — providing a quantitative feedback loop that validates the causal link between voice-agent interventions and churn reduction.

### Business ROI Statement

For HVAC service operators, customer churn and technician turnover represent the two most significant non-infrastructure cost centers: industry benchmarks place customer acquisition cost (CAC) at 5–7× retention cost, while technician replacement (recruiting, onboarding, certification) averages $8,000–$15,000 per hire. Project Aero attacks both vectors simultaneously. By intercepting inbound service calls before they escalate to negative reviews or cancellations, the voice agent functions as a real-time retention instrument — de-escalating frustrated customers, accelerating dispatch, and logging every interaction signal into the churn model. The 90-day predictive horizon provides operations managers with an intervention window that is actionable, not reactive: at-risk customers can receive proactive outreach, loyalty discounts, or priority scheduling before cancellation intent crystallizes. Similarly, technician churn signals (complaint frequency directed at internal processes, call sentiment involving scheduling conflicts, escalation routing patterns) give HR teams leading indicators rather than lagging exit surveys. Projected ROI at 500-account scale: 18–22% reduction in annual customer churn, 12–15% reduction in technician turnover, and an estimated $340,000–$580,000 in retained annual recurring revenue — all attributable to a system that operates autonomously 24/7 without incremental headcount.

---

## 2. System Architecture & Data Flow

### 2.1 High-Level Component Map

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

### 2.2 Detailed Sequence: High-Churn-Risk Inbound Call

The following describes the complete event sequence when an inbound call is received from a customer whose account is flagged as `risk_tier: HIGH`.

```
T+0ms    [PSTN] Customer dials HVAC company number
         → Vapi intercepts, assigns call_id: "call_abc123"
         → WebSocket stream established (16kHz PCM, Deepgram ASR)

T+50ms   [Vapi → FastAPI POST /webhook/vapi/call.started]
         Payload: { call_id, phone_number, timestamp }
         → CustomerService.lookup_by_phone() → PostgreSQL query
         → ChurnService.get_latest_score(customer_id) → returns { score: 0.82, tier: "HIGH" }
         → Vapi system_prompt updated dynamically with customer context:
           - name, equipment_age, last_service_date, open_tickets
           - INJECTED: "⚠️ HIGH CHURN RISK: Apply retention protocol. Offer priority dispatch."

T+200ms  [Vapi → Claude] Initial greeting rendered with personalized context
         "Hi [FirstName], I see your Carrier unit is 7 years old and your last service was 8 months ago..."

T+800ms  [Customer speaks] "Yeah my AC stopped working and I'm really frustrated, this is the third time..."
         → Deepgram produces partial transcript tokens (streaming)
         → Sentiment analyzer running in parallel: { compound: -0.74, label: "NEGATIVE" }

T+1200ms [Claude] Detects: intent=SERVICE_COMPLAINT, entities={equipment_issue, recurrence_flag}
         → Emits tool call: get_equipment_info({ customer_id, equipment_id })
         → FastAPI executes, returns full equipment history from PostgreSQL

T+1500ms [Claude] Detects escalation signal: "third time" → recurrence_complaint_count += 1
         → Emits tool call: query_churn_score({ customer_id })
         → Returns: { score: 0.82, top_features: ["escalation_frequency", "sentiment_degradation"] }
         → Claude receives HIGH risk signal, activates retention persona:
           "I completely understand your frustration. I'm escalating this as Priority 1..."

T+2100ms [Claude] Collects dispatch constraints from customer: preferred_time, access_instructions
         → Emits tool call: schedule_dispatch({
             customer_id, priority: "P1", issue_type: "AC_FAILURE",
             preferred_window: "tomorrow_AM", equipment_id, notes: "Third recurrence"
           })
         → DispatchService: finds available technician with relevant certification
         → Creates dispatch_job in PostgreSQL, returns job_id + ETA

T+3000ms [Claude] Confirms dispatch: "A certified technician will be there tomorrow between 8–10 AM.
         Your confirmation number is #DX-9821."

T+call_end [Vapi → FastAPI POST /webhook/vapi/call.ended]
         Full transcript emitted with word-level timestamps

T+0ms    [Async] TranscriptService.process(call_id)
         → Extracts feature vector (see §3.3)
         → Publishes to Kafka topic: "call.features"
         → FeaturePipeline consumes, upserts feature_store
         → ChurnModelInference re-scores account
         → New score: 0.61 (DOWN from 0.82) — retention intervention logged
         → Publishes to Kafka topic: "churn.scores"
         → Dashboard receives SSE update: "Saved by AI" event recorded
```

### 2.3 RAG Pipeline Architecture

```
KNOWLEDGE SOURCES (ingested at startup + nightly re-index):
  ├── FAQ documents (markdown → chunked → embedded)
  ├── Equipment service manuals (PDF → parsed → embedded)
  ├── Historical resolution patterns (structured → embedded)
  └── Warranty terms and pricing tables

EMBEDDING MODEL: text-embedding-3-small (OpenAI) → 1536-dim vectors
VECTOR STORE: Pinecone (serverless, us-east-1)
RETRIEVAL STRATEGY: Top-K=5 cosine similarity, MMR reranking
CONTEXT INJECTION: Retrieved chunks injected into Claude system prompt per-turn

QUERY FLOW:
  User utterance
    → Embedding (text-embedding-3-small)
    → Pinecone.query(vector, top_k=5, filter={namespace: "hvac_ops"})
    → Rerank by MMR (Maximal Marginal Relevance, lambda=0.5)
    → Format as: "RELEVANT CONTEXT:\n{chunk_1}\n{chunk_2}..."
    → Prepend to Claude next-turn system context
```

---

## 3. Database Schemas & Feature Store

### 3.1 PostgreSQL Schemas

#### 3.1.1 `customers` Table

```sql
CREATE TABLE customers (
  customer_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id         VARCHAR(64) UNIQUE,                    -- CRM/Salesforce ID
  full_name           VARCHAR(255) NOT NULL,
  phone_primary       VARCHAR(20) NOT NULL,
  phone_secondary     VARCHAR(20),
  email               VARCHAR(255),
  address_line1       VARCHAR(255),
  address_line2       VARCHAR(100),
  city                VARCHAR(100),
  state               CHAR(2),
  zip                 VARCHAR(10),
  account_status      VARCHAR(20) DEFAULT 'ACTIVE'           -- ACTIVE | SUSPENDED | CHURNED
                        CHECK (account_status IN ('ACTIVE','SUSPENDED','CHURNED','PROSPECT')),
  customer_since      DATE NOT NULL,
  contract_type       VARCHAR(30)                            -- ANNUAL_MAINTENANCE | RESIDENTIAL | COMMERCIAL
                        CHECK (contract_type IN ('ANNUAL_MAINTENANCE','RESIDENTIAL_OTC','COMMERCIAL_SLA')),
  contract_value_usd  NUMERIC(10, 2),
  payment_method      VARCHAR(30),
  preferred_tech_id   UUID REFERENCES technicians(technician_id),
  notes               TEXT,
  metadata            JSONB DEFAULT '{}',                    -- extensible KV store
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_customers_phone ON customers(phone_primary);
CREATE INDEX idx_customers_status ON customers(account_status);
CREATE INDEX idx_customers_churn_risk ON customers((metadata->>'churn_tier'));
```

#### 3.1.2 `equipment` Table

```sql
CREATE TABLE equipment (
  equipment_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id         UUID NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
  make                VARCHAR(100) NOT NULL,                  -- e.g., "Carrier", "Trane"
  model               VARCHAR(100) NOT NULL,
  serial_number       VARCHAR(100) UNIQUE,
  equipment_type      VARCHAR(50)                            -- AC_UNIT | FURNACE | HEAT_PUMP | AIR_HANDLER
                        CHECK (equipment_type IN ('AC_UNIT','FURNACE','HEAT_PUMP','AIR_HANDLER','MINI_SPLIT','OTHER')),
  install_date        DATE,
  warranty_expiry     DATE,
  last_service_date   DATE,
  service_count       INTEGER DEFAULT 0,
  age_years           NUMERIC(5,2) GENERATED ALWAYS AS (
                        EXTRACT(YEAR FROM AGE(NOW(), install_date))
                      ) STORED,
  efficiency_rating   VARCHAR(20),                           -- SEER rating, AFUE, etc.
  known_issues        TEXT[],                                -- array of issue tags
  manual_url          VARCHAR(500),                          -- Pinecone namespace key for manual embeddings
  metadata            JSONB DEFAULT '{}',
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

#### 3.1.3 `call_transcripts` Table

```sql
CREATE TABLE call_transcripts (
  transcript_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id             VARCHAR(128) UNIQUE NOT NULL,          -- Vapi call_id
  customer_id         UUID REFERENCES customers(customer_id),
  technician_id       UUID REFERENCES technicians(technician_id),
  dispatch_job_id     UUID REFERENCES dispatch_jobs(job_id),
  call_direction      CHAR(8) DEFAULT 'INBOUND'
                        CHECK (call_direction IN ('INBOUND', 'OUTBOUND')),
  call_start_utc      TIMESTAMPTZ NOT NULL,
  call_end_utc        TIMESTAMPTZ,
  duration_seconds    INTEGER,
  call_outcome        VARCHAR(50)                            -- DISPATCHED | FAQ_RESOLVED | ESCALATED | ABANDONED | RETAINED
                        CHECK (call_outcome IN ('DISPATCHED','FAQ_RESOLVED','ESCALATED_HUMAN','ABANDONED','RETAINED','VOICEMAIL')),
  -- Raw transcript storage
  transcript_raw      TEXT,                                  -- full concatenated text
  transcript_json     JSONB,                                 -- [{speaker, text, start_ms, end_ms, confidence}]
  -- Computed sentiment & signal fields (populated async post-call)
  sentiment_overall   NUMERIC(4,3) CHECK (sentiment_overall BETWEEN -1 AND 1),
  sentiment_trajectory JSONB,                               -- [{minute, score}] time-series
  dominant_intent     VARCHAR(50),                          -- COMPLAINT | SCHEDULING | FAQ | EMERGENCY
  intent_confidence   NUMERIC(4,3),
  entities_extracted  JSONB,                                -- {equipment_mentioned, issue_tags, urgency_words}
  escalation_detected BOOLEAN DEFAULT FALSE,
  hesitation_markers  JSONB,                                -- {pause_count, avg_pause_ms, filler_word_count}
  emotion_labels      JSONB,                                -- {anger, frustration, satisfaction, neutral} probabilities
  -- Churn signal flags
  churn_risk_at_call_start  NUMERIC(4,3),                  -- snapshot of score when call began
  churn_risk_at_call_end    NUMERIC(4,3),                  -- score after intervention
  intervention_successful   BOOLEAN,                        -- score dropped by >= 0.15
  -- RAG metadata
  rag_queries_issued  INTEGER DEFAULT 0,
  rag_chunks_used     JSONB,                                -- [{chunk_id, similarity_score, namespace}]
  -- Tool calls made during session
  tool_calls_log      JSONB,                                -- [{tool_name, args, result, latency_ms, timestamp}]
  -- Vapi metadata
  vapi_metadata       JSONB DEFAULT '{}',
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_transcripts_customer ON call_transcripts(customer_id);
CREATE INDEX idx_transcripts_outcome ON call_transcripts(call_outcome);
CREATE INDEX idx_transcripts_start ON call_transcripts(call_start_utc DESC);
CREATE INDEX idx_transcripts_intervention ON call_transcripts(intervention_successful) WHERE intervention_successful = TRUE;
```

#### 3.1.4 `technicians` Table

```sql
CREATE TABLE technicians (
  technician_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_number       VARCHAR(32) UNIQUE NOT NULL,
  full_name             VARCHAR(255) NOT NULL,
  phone                 VARCHAR(20),
  email                 VARCHAR(255),
  employment_status     VARCHAR(20) DEFAULT 'ACTIVE'
                          CHECK (employment_status IN ('ACTIVE','ON_LEAVE','TERMINATED','PROBATION')),
  hire_date             DATE NOT NULL,
  tenure_years          NUMERIC(5,2) GENERATED ALWAYS AS (
                          EXTRACT(YEAR FROM AGE(NOW(), hire_date))
                        ) STORED,
  certifications        TEXT[],                              -- ["EPA_608", "NATE_AC", "NATE_HEAT_PUMP"]
  service_zones         VARCHAR(20)[],                       -- zip codes or zone IDs
  avg_customer_rating   NUMERIC(3,2),                        -- rolling 90-day avg
  jobs_completed_90d    INTEGER DEFAULT 0,
  complaints_received_90d INTEGER DEFAULT 0,
  scheduled_jobs        JSONB DEFAULT '[]',                  -- upcoming dispatch slots
  churn_risk_score      NUMERIC(4,3) DEFAULT 0.0,            -- employee churn probability
  churn_risk_tier       VARCHAR(10) DEFAULT 'LOW'
                          CHECK (churn_risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  hr_flags              JSONB DEFAULT '[]',                  -- [{flag_type, date, notes}]
  metadata              JSONB DEFAULT '{}',
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);
```

#### 3.1.5 `dispatch_jobs` Table

```sql
CREATE TABLE dispatch_jobs (
  job_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_number            VARCHAR(20) UNIQUE NOT NULL,          -- human-readable: "DX-9821"
  customer_id           UUID NOT NULL REFERENCES customers(customer_id),
  equipment_id          UUID REFERENCES equipment(equipment_id),
  technician_id         UUID REFERENCES technicians(technician_id),
  call_transcript_id    UUID REFERENCES call_transcripts(transcript_id),
  job_status            VARCHAR(20) DEFAULT 'SCHEDULED'
                          CHECK (job_status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED','RESCHEDULED')),
  priority              CHAR(2) DEFAULT 'P3'
                          CHECK (priority IN ('P1','P2','P3','P4')),          -- P1 = emergency
  issue_type            VARCHAR(50) NOT NULL,
  issue_description     TEXT,
  scheduled_window_start TIMESTAMPTZ,
  scheduled_window_end  TIMESTAMPTZ,
  actual_arrival        TIMESTAMPTZ,
  actual_completion     TIMESTAMPTZ,
  resolution_notes      TEXT,
  parts_used            JSONB DEFAULT '[]',                   -- [{part_id, name, cost}]
  labor_hours           NUMERIC(4,2),
  invoice_amount_usd    NUMERIC(10,2),
  customer_rating       SMALLINT CHECK (customer_rating BETWEEN 1 AND 5),
  customer_feedback     TEXT,
  created_by            VARCHAR(20) DEFAULT 'VOICE_AGENT',   -- VOICE_AGENT | MANUAL | API
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_customer ON dispatch_jobs(customer_id);
CREATE INDEX idx_jobs_tech ON dispatch_jobs(technician_id, scheduled_window_start);
CREATE INDEX idx_jobs_status ON dispatch_jobs(job_status);
```

#### 3.1.6 `churn_scores` Table (Time-Series)

```sql
CREATE TABLE churn_scores (
  score_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type           CHAR(8) NOT NULL CHECK (entity_type IN ('CUSTOMER', 'EMPLOYEE')),
  entity_id             UUID NOT NULL,                        -- FK to customers or technicians
  score_timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  churn_probability     NUMERIC(4,3) NOT NULL,                -- 0.000–1.000
  risk_tier             VARCHAR(10) NOT NULL
                          CHECK (risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  -- Top feature contributions (SHAP values)
  feature_contributions JSONB,                               -- [{feature_name, shap_value, direction}]
  model_version         VARCHAR(20),                          -- "xgb_v2.1.0"
  scoring_trigger       VARCHAR(30),                         -- CALL_END | SCHEDULED_BATCH | MANUAL
  -- Horizon: what score predicts
  prediction_horizon_days INTEGER DEFAULT 90,
  -- Intervention tracking
  intervention_applied  BOOLEAN DEFAULT FALSE,
  intervention_type     VARCHAR(50),                         -- PRIORITY_DISPATCH | LOYALTY_OFFER | PROACTIVE_CALL
  post_intervention_score NUMERIC(4,3),
  score_delta           NUMERIC(5,3) GENERATED ALWAYS AS (
                          COALESCE(post_intervention_score, churn_probability) - churn_probability
                        ) STORED
);

CREATE INDEX idx_churn_entity ON churn_scores(entity_type, entity_id, score_timestamp DESC);
CREATE INDEX idx_churn_tier ON churn_scores(risk_tier, score_timestamp DESC);

-- Hypertable if using TimescaleDB extension:
-- SELECT create_hypertable('churn_scores', 'score_timestamp');
```

#### 3.1.7 `feature_store` Table

```sql
CREATE TABLE feature_store (
  feature_record_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type           CHAR(8) NOT NULL CHECK (entity_type IN ('CUSTOMER', 'EMPLOYEE')),
  entity_id             UUID NOT NULL,
  computed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  window_start          TIMESTAMPTZ NOT NULL,                 -- feature window start
  window_end            TIMESTAMPTZ NOT NULL,                 -- feature window end (= computed_at)
  window_days           INTEGER NOT NULL DEFAULT 90,

  -- ── VOICE / INTERACTION FEATURES ─────────────────────────────────────────
  total_calls_window          INTEGER DEFAULT 0,
  inbound_call_count          INTEGER DEFAULT 0,
  outbound_call_count         INTEGER DEFAULT 0,
  avg_call_duration_seconds   NUMERIC(8,2),
  escalation_frequency        NUMERIC(5,4),                  -- escalations / total_calls
  escalation_count            INTEGER DEFAULT 0,
  sentiment_first_call        NUMERIC(4,3),                  -- sentiment of first call in window
  sentiment_last_call         NUMERIC(4,3),                  -- sentiment of most recent call
  sentiment_degradation_slope NUMERIC(6,4),                  -- OLS slope of sentiment over time
  sentiment_std_dev           NUMERIC(5,4),                  -- volatility of sentiment
  avg_sentiment_score         NUMERIC(4,3),
  min_sentiment_score         NUMERIC(4,3),
  negative_call_ratio         NUMERIC(5,4),                  -- calls with sentiment < -0.3 / total
  hesitation_marker_rate      NUMERIC(6,4),                  -- avg hesitation events per call
  filler_word_rate            NUMERIC(6,4),                  -- um/uh/like per 100 words
  anger_emotion_ratio         NUMERIC(5,4),                  -- calls with anger_score > 0.6 / total
  complaint_mention_count     INTEGER DEFAULT 0,
  recurrence_complaint_count  INTEGER DEFAULT 0,             -- complaints mentioning "again", "third time"

  -- ── OPERATIONAL FEATURES ─────────────────────────────────────────────────
  avg_time_to_resolution_hours    NUMERIC(8,2),
  time_to_resolution_std_dev      NUMERIC(8,2),
  max_time_to_resolution_hours    NUMERIC(8,2),
  dispatch_cancellation_rate      NUMERIC(5,4),              -- cancelled jobs / scheduled jobs
  rescheduling_count              INTEGER DEFAULT 0,
  open_ticket_age_days_avg        NUMERIC(8,2),
  open_ticket_count               INTEGER DEFAULT 0,
  p1_p2_job_count                 INTEGER DEFAULT 0,         -- high-priority dispatches in window
  same_issue_recurrence_count     INTEGER DEFAULT 0,         -- same issue_type within window
  technician_change_count         INTEGER DEFAULT 0,         -- # of different techs dispatched

  -- ── ACCOUNT / BEHAVIORAL FEATURES ────────────────────────────────────────
  payment_delay_days_avg          NUMERIC(8,2),
  payment_failure_count           INTEGER DEFAULT 0,
  days_since_last_positive_call   INTEGER,
  days_since_last_service         INTEGER,
  contract_days_until_renewal     INTEGER,
  customer_rating_avg_90d         NUMERIC(3,2),
  equipment_age_years             NUMERIC(5,2),
  warranty_expired                BOOLEAN DEFAULT FALSE,

  -- ── EMPLOYEE-SPECIFIC FEATURES (only populated for entity_type='EMPLOYEE') ──
  complaint_rate_90d              NUMERIC(5,4),              -- complaints received / jobs completed
  avg_customer_rating_90d         NUMERIC(3,2),
  schedule_conflict_count         INTEGER DEFAULT 0,         -- proxy for frustration with scheduling
  overtime_hours_90d              NUMERIC(8,2),
  internal_escalation_count       INTEGER DEFAULT 0,

  -- ── RAW FEATURE VECTOR (for model serving) ───────────────────────────────
  feature_vector                  VECTOR(64),                -- pgvector compressed feature embedding

  UNIQUE(entity_type, entity_id, window_end, window_days)
);

CREATE INDEX idx_features_entity ON feature_store(entity_type, entity_id, computed_at DESC);
```

### 3.2 Feature Vector Definition (90-Day Churn Model Inputs)

The following 34 scalar features constitute the primary input tensor `X` fed to the churn ensemble. Features are standardized (μ=0, σ=1) using sklearn's `StandardScaler` fitted on training data; the scaler artifact is versioned alongside the model.

```python
# Feature engineering specification
# Source: feature_store table, one row per entity per scoring event

CHURN_FEATURE_SCHEMA = {
    # === VOICE / SENTIMENT SIGNALS (highest predictive weight) ===
    "escalation_frequency":           {"dtype": "float32", "range": [0.0, 1.0],  "null_strategy": "fill_0"},
    "sentiment_degradation_slope":    {"dtype": "float32", "range": [-2.0, 2.0], "null_strategy": "fill_0"},
    "avg_sentiment_score":            {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "min_sentiment_score":            {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "negative_call_ratio":            {"dtype": "float32", "range": [0.0, 1.0],  "null_strategy": "fill_0"},
    "anger_emotion_ratio":            {"dtype": "float32", "range": [0.0, 1.0],  "null_strategy": "fill_0"},
    "recurrence_complaint_count":     {"dtype": "int16",   "range": [0, 50],     "null_strategy": "fill_0"},
    "hesitation_marker_rate":         {"dtype": "float32", "range": [0.0, 5.0],  "null_strategy": "fill_0"},
    "sentiment_std_dev":              {"dtype": "float32", "range": [0.0, 2.0],  "null_strategy": "fill_0"},
    "sentiment_first_call":           {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "sentiment_last_call":            {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},

    # === OPERATIONAL SIGNALS ===
    "avg_time_to_resolution_hours":   {"dtype": "float32", "range": [0.0, 720.0],"null_strategy": "fill_mean"},
    "time_to_resolution_std_dev":     {"dtype": "float32", "range": [0.0, 500.0],"null_strategy": "fill_0"},
    "dispatch_cancellation_rate":     {"dtype": "float32", "range": [0.0, 1.0],  "null_strategy": "fill_0"},
    "rescheduling_count":             {"dtype": "int16",   "range": [0, 20],     "null_strategy": "fill_0"},
    "open_ticket_age_days_avg":       {"dtype": "float32", "range": [0.0, 365.0],"null_strategy": "fill_0"},
    "open_ticket_count":              {"dtype": "int16",   "range": [0, 30],     "null_strategy": "fill_0"},
    "p1_p2_job_count":               {"dtype": "int16",   "range": [0, 20],     "null_strategy": "fill_0"},
    "same_issue_recurrence_count":    {"dtype": "int16",   "range": [0, 20],     "null_strategy": "fill_0"},
    "technician_change_count":        {"dtype": "int16",   "range": [0, 15],     "null_strategy": "fill_0"},

    # === ACCOUNT / BEHAVIORAL SIGNALS ===
    "total_calls_window":             {"dtype": "int16",   "range": [0, 200],    "null_strategy": "fill_0"},
    "payment_delay_days_avg":         {"dtype": "float32", "range": [0.0, 180.0],"null_strategy": "fill_0"},
    "payment_failure_count":          {"dtype": "int16",   "range": [0, 20],     "null_strategy": "fill_0"},
    "days_since_last_positive_call":  {"dtype": "int16",   "range": [0, 365],    "null_strategy": "fill_365"},
    "days_since_last_service":        {"dtype": "int16",   "range": [0, 730],    "null_strategy": "fill_730"},
    "contract_days_until_renewal":    {"dtype": "int16",   "range": [-365, 730], "null_strategy": "fill_0"},
    "equipment_age_years":            {"dtype": "float32", "range": [0.0, 30.0], "null_strategy": "fill_mean"},
    "warranty_expired":               {"dtype": "bool",    "range": [0, 1],      "null_strategy": "fill_0"},
    "customer_rating_avg_90d":        {"dtype": "float32", "range": [1.0, 5.0],  "null_strategy": "fill_mean"},
    "escalation_count":               {"dtype": "int16",   "range": [0, 50],     "null_strategy": "fill_0"},

    # === DERIVED / INTERACTION FEATURES (engineered) ===
    "sentiment_x_escalation":         {"dtype": "float32", "computed": "avg_sentiment_score * escalation_frequency"},
    "resolution_x_recurrence":        {"dtype": "float32", "computed": "avg_time_to_resolution_hours * same_issue_recurrence_count"},
    "payment_x_sentiment":            {"dtype": "float32", "computed": "payment_failure_count * (1 + abs(min_sentiment_score))"},
    "composite_risk_index":           {"dtype": "float32", "computed": "(negative_call_ratio * 0.3) + (escalation_frequency * 0.4) + (sentiment_degradation_slope * -0.3)"},
}

# Risk tier thresholds (calibrated on validation set, Youden J optimal cutpoint)
RISK_TIERS = {
    "LOW":      (0.000, 0.350),
    "MEDIUM":   (0.350, 0.600),
    "HIGH":     (0.600, 0.800),
    "CRITICAL": (0.800, 1.000),
}

# Model ensemble weights (tuned via Optuna, 5-fold CV, AUC-ROC objective)
ENSEMBLE_WEIGHTS = {
    "xgboost":       0.55,
    "lightgbm":      0.35,
    "isolation_forest_anomaly_score": 0.10,  # outlier detection supplement
}
```

---

## 4. API Contracts & Tool Calling

### 4.1 FastAPI Webhook Endpoint Contract

```
POST /webhook/vapi
Content-Type: application/json
X-Vapi-Secret: {VAPI_WEBHOOK_SECRET}  # HMAC-SHA256 verified

Request Body (Vapi event envelope):
{
  "message": {
    "type": "tool-calls",          // or "call-start", "call-end", "transcript"
    "call": { "id": "string", "phoneNumber": {...} },
    "toolCallList": [...]          // populated for type="tool-calls"
  }
}

Response (for tool-calls type):
{
  "results": [
    {
      "toolCallId": "string",
      "result": "string"          // JSON-stringified result
    }
  ]
}
```

### 4.2 Claude Tool-Calling Schemas (JSON Schema format)

These tool definitions are registered with Vapi and passed to the Claude inference context. Claude emits structured `tool_use` blocks; FastAPI's tool execution layer deserializes and dispatches.

#### Tool 1: `schedule_dispatch`

```json
{
  "name": "schedule_dispatch",
  "description": "Create a service dispatch job for an HVAC technician. Use when the customer needs in-person service, repair, or maintenance. Returns a confirmation number and estimated arrival window.",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": {
        "type": "string",
        "description": "UUID of the customer account"
      },
      "equipment_id": {
        "type": "string",
        "description": "UUID of the specific equipment unit requiring service"
      },
      "issue_type": {
        "type": "string",
        "enum": [
          "AC_NO_COOLING", "AC_NOISY", "AC_LEAKING", "FURNACE_NO_HEAT",
          "FURNACE_NOISY", "HEAT_PUMP_FAILURE", "THERMOSTAT_ISSUE",
          "REFRIGERANT_LEAK", "ELECTRICAL_FAULT", "PREVENTIVE_MAINTENANCE",
          "EMERGENCY_BREAKDOWN", "WARRANTY_CLAIM", "FILTER_REPLACEMENT", "OTHER"
        ],
        "description": "Categorized issue type for dispatch routing and technician skill matching"
      },
      "priority": {
        "type": "string",
        "enum": ["P1", "P2", "P3", "P4"],
        "description": "P1=Emergency (same-day), P2=Urgent (next-day), P3=Standard (2-3 days), P4=Scheduled (flexible)"
      },
      "preferred_window": {
        "type": "string",
        "description": "Customer's preferred service window in natural language: e.g., 'tomorrow morning', 'this Saturday afternoon', 'any weekday next week'"
      },
      "issue_description": {
        "type": "string",
        "description": "Verbatim summary of the customer's issue description as stated on the call"
      },
      "access_instructions": {
        "type": "string",
        "description": "Any special access instructions for the property (gate codes, pet warnings, entry procedures)"
      },
      "churn_risk_context": {
        "type": "object",
        "description": "Churn risk snapshot to influence dispatch priority augmentation",
        "properties": {
          "risk_tier": { "type": "string" },
          "score": { "type": "number" }
        }
      }
    },
    "required": ["customer_id", "issue_type", "priority", "preferred_window", "issue_description"]
  }
}
```

**FastAPI handler response schema:**
```json
{
  "success": true,
  "job_id": "3f8a2c1e-...",
  "job_number": "DX-9821",
  "technician": {
    "name": "Marcus T.",
    "certifications": ["NATE_AC", "EPA_608"],
    "rating": 4.8
  },
  "scheduled_window": {
    "start": "2025-06-01T08:00:00-07:00",
    "end": "2025-06-01T10:00:00-07:00"
  },
  "priority_applied": "P1",
  "retention_flag": true,
  "human_readable": "Marcus will arrive tomorrow between 8–10 AM. Confirmation: DX-9821."
}
```

#### Tool 2: `query_churn_score`

```json
{
  "name": "query_churn_score",
  "description": "Retrieve the current 90-day churn probability and risk tier for a customer. Use when you need to determine whether to apply retention protocols, offer concessions, or escalate priority.",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": {
        "type": "string",
        "description": "UUID of the customer account"
      }
    },
    "required": ["customer_id"]
  }
}
```

**Response schema:**
```json
{
  "customer_id": "abc123...",
  "churn_probability": 0.82,
  "risk_tier": "HIGH",
  "top_contributing_features": [
    { "feature": "escalation_frequency", "shap_value": 0.31, "direction": "INCREASES_RISK" },
    { "feature": "sentiment_degradation_slope", "shap_value": 0.24, "direction": "INCREASES_RISK" },
    { "feature": "same_issue_recurrence_count", "shap_value": 0.19, "direction": "INCREASES_RISK" }
  ],
  "recommended_interventions": [
    "PRIORITY_DISPATCH",
    "LOYALTY_DISCOUNT_OFFER",
    "MANAGER_CALLBACK"
  ],
  "score_age_minutes": 14,
  "last_scored_at": "2025-05-30T11:42:00Z"
}
```

#### Tool 3: `get_customer_info`

```json
{
  "name": "get_customer_info",
  "description": "Retrieve full customer profile including account status, equipment inventory, service history summary, and open tickets. Always call this first when a call starts if customer_id is not yet in context.",
  "parameters": {
    "type": "object",
    "properties": {
      "lookup_method": {
        "type": "string",
        "enum": ["phone", "customer_id", "email"],
        "description": "Field to use for lookup"
      },
      "lookup_value": {
        "type": "string",
        "description": "The phone number, customer_id, or email to look up"
      }
    },
    "required": ["lookup_method", "lookup_value"]
  }
}
```

#### Tool 4: `get_equipment_info`

```json
{
  "name": "get_equipment_info",
  "description": "Retrieve detailed equipment record including model, age, service history, known issues, and warranty status. Use when customer mentions a specific unit or when diagnosing issues.",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string" },
      "equipment_id": {
        "type": "string",
        "description": "Specific equipment UUID. If omitted, returns all equipment for customer."
      }
    },
    "required": ["customer_id"]
  }
}
```

#### Tool 5: `rag_knowledge_query`

```json
{
  "name": "rag_knowledge_query",
  "description": "Search the HVAC knowledge base (FAQs, equipment manuals, troubleshooting guides, warranty terms) to answer customer questions. Use when customer asks a technical question you cannot answer from customer profile data alone.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The customer's question or topic to search, in natural language"
      },
      "equipment_model": {
        "type": "string",
        "description": "Optional: filter search to documents specific to this equipment model"
      },
      "namespace": {
        "type": "string",
        "enum": ["faq_general", "equipment_manuals", "warranty_terms", "troubleshooting", "pricing"],
        "description": "Optional: scope the vector search to a specific knowledge namespace"
      },
      "top_k": {
        "type": "integer",
        "default": 5,
        "description": "Number of chunks to retrieve (1–10)"
      }
    },
    "required": ["query"]
  }
}
```

#### Tool 6: `create_support_ticket`

```json
{
  "name": "create_support_ticket",
  "description": "Create an unresolved support issue ticket for cases that cannot be resolved on the current call (requires human follow-up, manager escalation, warranty claims, billing disputes).",
  "parameters": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string" },
      "ticket_type": {
        "type": "string",
        "enum": ["BILLING_DISPUTE", "WARRANTY_CLAIM", "COMPLAINT_ESCALATION", "SAFETY_CONCERN", "REFUND_REQUEST", "MANAGER_CALLBACK", "UNRESOLVED_TECHNICAL"]
      },
      "subject": { "type": "string", "description": "One-line ticket subject" },
      "description": { "type": "string", "description": "Full description of issue with customer's verbatim complaint" },
      "priority": { "type": "string", "enum": ["P1", "P2", "P3"] },
      "preferred_callback_time": { "type": "string" }
    },
    "required": ["customer_id", "ticket_type", "subject", "description", "priority"]
  }
}
```

### 4.3 Internal REST API Endpoints (FastAPI)

```
# Churn Engine Endpoints
GET    /api/v1/churn/scores?entity_type=CUSTOMER&risk_tier=HIGH&limit=50
GET    /api/v1/churn/scores/{entity_id}/history?days=90
POST   /api/v1/churn/scores/{entity_id}/trigger          # force re-score
GET    /api/v1/churn/cohorts?window_days=90&bucket_count=10

# Customer Endpoints
GET    /api/v1/customers?search={q}&page={n}&limit={n}
GET    /api/v1/customers/{customer_id}
PATCH  /api/v1/customers/{customer_id}
GET    /api/v1/customers/{customer_id}/transcripts
GET    /api/v1/customers/{customer_id}/churn-timeline

# Analytics Endpoints (consumed by dashboard)
GET    /api/v1/analytics/retention-events?start={iso}&end={iso}
GET    /api/v1/analytics/churn-probability-distribution
GET    /api/v1/analytics/saved-by-ai?start={iso}&end={iso}
GET    /api/v1/analytics/feature-importance?model_version=latest

# SSE Stream (dashboard real-time updates)
GET    /api/v1/stream/churn-events          # Server-Sent Events
```

---

## 5. Visualization Specifications

### 5.1 Dashboard Data Contracts

#### 5.1.1 Churn Risk Distribution (Donut + KPI Cards)

```typescript
// GET /api/v1/analytics/churn-probability-distribution
// Response type:
interface ChurnDistributionResponse {
  as_of: string;                       // ISO timestamp
  total_customers: number;
  cohorts: {
    tier: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
    count: number;
    percentage: number;
    avg_score: number;
    estimated_arr_at_risk_usd: number; // count * avg_contract_value
  }[];
  week_over_week_delta: {
    tier: string;
    delta_count: number;               // positive = more at risk
    delta_percentage: number;
  }[];
}

// Example payload:
{
  "as_of": "2025-05-30T12:00:00Z",
  "total_customers": 487,
  "cohorts": [
    { "tier": "LOW",      "count": 312, "percentage": 64.1, "avg_score": 0.18, "estimated_arr_at_risk_usd": 0 },
    { "tier": "MEDIUM",   "count": 98,  "percentage": 20.1, "avg_score": 0.48, "estimated_arr_at_risk_usd": 156400 },
    { "tier": "HIGH",     "count": 57,  "percentage": 11.7, "avg_score": 0.71, "estimated_arr_at_risk_usd": 227100 },
    { "tier": "CRITICAL", "count": 20,  "percentage": 4.1,  "avg_score": 0.91, "estimated_arr_at_risk_usd": 142000 }
  ],
  "week_over_week_delta": [
    { "tier": "CRITICAL", "delta_count": -3, "delta_percentage": -0.6 }
  ]
}
```

**Recharts component:** `<PieChart>` with `<Cell>` colors `{LOW: "#22c55e", MEDIUM: "#f59e0b", HIGH: "#f97316", CRITICAL: "#ef4444"}`. KPI cards overlay: Total ARR at Risk, Active High-Risk Accounts, Avg Score (portfolio).

#### 5.1.2 Churn Probability Time-Series (Line Chart with Intervention Markers)

```typescript
// GET /api/v1/customers/{customer_id}/churn-timeline
interface ChurnTimelineResponse {
  customer_id: string;
  customer_name: string;
  data_points: {
    timestamp: string;                  // ISO
    churn_probability: number;
    risk_tier: string;
    event?: {
      type: "CALL_START" | "DISPATCH_CREATED" | "INTERVENTION_APPLIED" | "TICKET_RESOLVED" | "CHURNED";
      label: string;                    // e.g., "Priority Dispatch Scheduled"
      call_id?: string;
    };
  }[];
  current_score: number;
  score_90d_ago: number;
  net_change: number;                   // negative = improving
  interventions_count: number;
  saved_by_ai: boolean;
}

// Example payload (visualizes a retention success story):
{
  "customer_id": "cust_abc123",
  "customer_name": "Sarah M.",
  "data_points": [
    { "timestamp": "2025-03-01T00:00:00Z", "churn_probability": 0.24, "risk_tier": "LOW" },
    { "timestamp": "2025-03-15T00:00:00Z", "churn_probability": 0.38, "risk_tier": "MEDIUM" },
    { "timestamp": "2025-04-01T00:00:00Z", "churn_probability": 0.61, "risk_tier": "HIGH" },
    { "timestamp": "2025-04-08T00:00:00Z", "churn_probability": 0.79, "risk_tier": "HIGH",
      "event": { "type": "CALL_START", "label": "Inbound complaint: 3rd recurrence" } },
    { "timestamp": "2025-04-08T01:00:00Z", "churn_probability": 0.79 },
    { "timestamp": "2025-04-08T02:00:00Z", "churn_probability": 0.62,
      "event": { "type": "INTERVENTION_APPLIED", "label": "P1 Dispatch + Loyalty Offer Applied" } },
    { "timestamp": "2025-04-10T00:00:00Z", "churn_probability": 0.44, "risk_tier": "MEDIUM" },
    { "timestamp": "2025-04-20T00:00:00Z", "churn_probability": 0.28, "risk_tier": "LOW" },
    { "timestamp": "2025-05-01T00:00:00Z", "churn_probability": 0.19, "risk_tier": "LOW" }
  ],
  "current_score": 0.19,
  "score_90d_ago": 0.24,
  "net_change": -0.05,
  "interventions_count": 1,
  "saved_by_ai": true
}
```

**Recharts component:** `<LineChart>` with `<ReferenceLine>` at 0.60 (HIGH threshold) and 0.80 (CRITICAL threshold). Intervention events rendered as `<ReferenceDot>` with custom `<Label>`. "Saved by AI" badge overlaid when `net_change < -0.15 AND saved_by_ai = true`.

#### 5.1.3 90-Day Risk Cohort Heatmap

```typescript
// GET /api/v1/churn/cohorts?window_days=90&bucket_count=10
interface CohortHeatmapResponse {
  generated_at: string;
  buckets: {
    score_range_low: number;            // e.g., 0.0
    score_range_high: number;           // e.g., 0.1
    customer_count: number;
    avg_arr_usd: number;
    intervention_success_rate: number;  // % where intervention lowered score by >=0.15
    top_features: string[];             // top 3 features in this cohort
    customers_sample: {                 // for drill-down tooltip
      customer_id: string;
      name: string;
      score: number;
    }[];
  }[];
}
```

**Recharts component:** Custom heatmap using `<ScatterChart>` where x=score_bucket, y=arr_at_risk, size=customer_count, color=intervention_success_rate (green-to-red gradient).

#### 5.1.4 "Saved by AI" Retention Metrics (KPI Dashboard Section)

```typescript
// GET /api/v1/analytics/saved-by-ai?start=2025-01-01&end=2025-05-30
interface SavedByAIResponse {
  period_start: string;
  period_end: string;
  total_high_risk_calls: number;        // calls where churn_risk_at_call_start > 0.6
  successful_interventions: number;     // score dropped >= 0.15 post-call
  intervention_success_rate: number;    // %
  estimated_arr_retained_usd: number;  // interventions * avg_contract_value
  avg_score_reduction: number;          // mean(churn_risk_at_call_start - churn_risk_at_call_end)
  monthly_trend: {
    month: string;                      // "2025-03"
    interventions: number;
    arr_retained_usd: number;
    success_rate: number;
  }[];
  top_intervention_types: {
    type: string;
    count: number;
    avg_score_reduction: number;
  }[];
}
```

**Tremor components:** `<Metric>` for ARR retained, `<BadgeDelta>` for success rate vs. prior period, `<AreaChart>` for monthly_trend.

#### 5.1.5 Real-Time Live Call Feed (SSE Consumer)

```typescript
// SSE: GET /api/v1/stream/churn-events
// Event stream format:

// Event type 1: Active call with risk signal
data: {
  "event_type": "CALL_ACTIVE",
  "call_id": "call_abc123",
  "customer_id": "cust_xyz789",
  "customer_name": "Robert K.",
  "churn_risk_tier": "CRITICAL",
  "churn_probability": 0.88,
  "call_duration_seconds": 142,
  "current_sentiment": -0.71,
  "dominant_intent": "COMPLAINT",
  "intervention_triggered": true,
  "timestamp": "2025-05-30T14:32:11Z"
}

// Event type 2: Intervention completed
data: {
  "event_type": "INTERVENTION_COMPLETE",
  "call_id": "call_abc123",
  "customer_id": "cust_xyz789",
  "score_before": 0.88,
  "score_after": 0.59,
  "delta": -0.29,
  "intervention_type": "PRIORITY_DISPATCH",
  "saved_by_ai": true,
  "job_number": "DX-9821",
  "timestamp": "2025-05-30T14:38:44Z"
}

// Event type 3: Batch churn re-score completed
data: {
  "event_type": "BATCH_SCORE_COMPLETE",
  "accounts_scored": 487,
  "new_critical": 3,
  "resolved_critical": 5,
  "timestamp": "2025-05-30T18:00:01Z"
}
```

**Frontend:** Toast notifications for CALL_ACTIVE (CRITICAL tier). Live activity feed using `<ScrollArea>` (Tremor) with event cards. Ticker for "Accounts saved today: N".

---

## 6. Cursor Implementation Plan

> **For Cursor:** Execute phases sequentially. Each phase is atomic — complete all files in a phase before proceeding. All Python files use type hints, Pydantic v2 models, and async/await patterns. All file paths are relative to the project root `hvac-intelligence/`.

### Phase 0: Project Scaffold & Environment

```bash
# Execute to initialize monorepo structure:
mkdir -p hvac-intelligence
cd hvac-intelligence
git init

# Directory structure to create:
# hvac-intelligence/
# ├── backend/               (FastAPI Python service)
# │   ├── app/
# │   │   ├── api/           (route handlers)
# │   │   ├── services/      (business logic)
# │   │   ├── models/        (Pydantic + SQLAlchemy)
# │   │   ├── ml/            (churn engine)
# │   │   ├── rag/           (RAG pipeline)
# │   │   ├── pipeline/      (Kafka + feature engineering)
# │   │   ├── core/          (config, db, deps)
# │   │   └── utils/
# │   ├── alembic/           (migrations)
# │   ├── tests/
# │   ├── requirements.txt
# │   └── Dockerfile
# ├── frontend/              (Next.js 14 dashboard)
# │   ├── app/
# │   ├── components/
# │   ├── lib/
# │   ├── types/
# │   └── Dockerfile
# ├── ml/                    (model training notebooks + artifacts)
# │   ├── notebooks/
# │   ├── artifacts/
# │   └── training/
# ├── infra/                 (Docker Compose, K8s manifests)
# ├── scripts/               (DB seed, data migration)
# └── docs/
```

**Files to create in Phase 0:**

```
hvac-intelligence/.env.example
hvac-intelligence/.env.local
hvac-intelligence/docker-compose.yml
hvac-intelligence/backend/requirements.txt
hvac-intelligence/backend/Dockerfile
hvac-intelligence/backend/app/__init__.py
hvac-intelligence/backend/app/core/config.py
hvac-intelligence/backend/app/core/database.py
hvac-intelligence/backend/app/core/logging.py
```

**`backend/requirements.txt`** (exact versions):
```
fastapi==0.111.0
uvicorn[standard]==0.30.1
pydantic==2.7.1
pydantic-settings==2.3.0
sqlalchemy==2.0.30
asyncpg==0.29.0
alembic==1.13.1
psycopg2-binary==2.9.9
anthropic==0.28.0
langchain==0.2.3
langchain-openai==0.1.8
langchain-pinecone==0.1.1
pinecone-client==4.1.0
openai==1.30.3
kafka-python==2.0.2
celery==5.4.0
redis==5.0.6
httpx==0.27.0
python-jose==3.3.0
passlib==1.7.4
python-multipart==0.0.9
xgboost==2.0.3
lightgbm==4.3.0
scikit-learn==1.5.0
pandas==2.2.2
numpy==1.26.4
shap==0.45.1
transformers==4.41.1        # for sentiment analysis (distilbert)
torch==2.3.0                 # CPU-only for inference
pytest==8.2.1
pytest-asyncio==0.23.7
httpx==0.27.0
```

**`backend/app/core/config.py`:**
```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "HVAC-Intelligence API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str                    # postgresql+asyncpg://user:pass@host:5432/hvac_intel
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # AI Services
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str                  # for embeddings
    VAPI_API_KEY: str
    VAPI_WEBHOOK_SECRET: str
    VAPI_ASSISTANT_ID: str
    
    # Vector DB
    PINECONE_API_KEY: str
    PINECONE_ENVIRONMENT: str            # "us-east-1"
    PINECONE_INDEX_NAME: str = "hvac-knowledge"
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str        # "localhost:9092"
    KAFKA_TOPIC_CALL_FEATURES: str = "call.features"
    KAFKA_TOPIC_CHURN_SCORES: str = "churn.scores"
    KAFKA_TOPIC_HIGH_RISK_ALERTS: str = "alerts.high_risk"
    
    # Redis / Celery
    REDIS_URL: str                       # "redis://localhost:6379/0"
    
    # ML Model
    MODEL_ARTIFACTS_PATH: str = "/app/ml/artifacts"
    CHURN_SCORE_THRESHOLD_HIGH: float = 0.60
    CHURN_SCORE_THRESHOLD_CRITICAL: float = 0.80
    FEATURE_WINDOW_DAYS: int = 90
    SCORING_CADENCE_HOURS: int = 6

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

**`docker-compose.yml`:**
```yaml
version: "3.9"
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: hvac_intel
      POSTGRES_USER: hvac_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  kafka:
    image: confluentinc/cp-kafka:7.6.1
    depends_on: [zookeeper]
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    ports: ["9092:9092"]

  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.1
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis, kafka]
    volumes: ["./ml/artifacts:/app/ml/artifacts"]

  celery-worker:
    build: ./backend
    command: celery -A app.pipeline.celery_app worker -Q features,scoring -c 4
    env_file: .env
    depends_on: [redis, kafka, postgres]

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    env_file: .env.local
    depends_on: [backend]

volumes:
  pgdata:
```

---

### Phase 1: Database Layer & Migrations

**Files to create:**
```
backend/app/models/__init__.py
backend/app/models/customer.py
backend/app/models/equipment.py
backend/app/models/call_transcript.py
backend/app/models/technician.py
backend/app/models/dispatch_job.py
backend/app/models/churn_score.py
backend/app/models/feature_store.py
backend/alembic/env.py
backend/alembic/versions/001_initial_schema.py
scripts/seed_database.py
```

**`backend/app/models/customer.py`** (SQLAlchemy 2.0 mapped dataclass style):
```python
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Numeric, Date, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.core.database import Base
import uuid

class Customer(Base):
    __tablename__ = "customers"
    
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_primary: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phone_secondary: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(2))
    zip: Mapped[Optional[str]] = mapped_column(String(10))
    account_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    customer_since: Mapped[date] = mapped_column(Date, nullable=False)
    contract_type: Mapped[Optional[str]] = mapped_column(String(30))
    contract_value_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    equipment: Mapped[list["Equipment"]] = relationship(back_populates="customer")
    transcripts: Mapped[list["CallTranscript"]] = relationship(back_populates="customer")
    dispatch_jobs: Mapped[list["DispatchJob"]] = relationship(back_populates="customer")
    churn_scores: Mapped[list["ChurnScore"]] = relationship(
        primaryjoin="and_(ChurnScore.entity_id==Customer.customer_id, ChurnScore.entity_type=='CUSTOMER')",
        foreign_keys="ChurnScore.entity_id"
    )
```

> **Cursor:** Implement all remaining model files following the same SQLAlchemy 2.0 mapped_column pattern as `customer.py`, mapping each column from §3.1 exactly. After all models are created, run `alembic init alembic` and `alembic revision --autogenerate -m "initial_schema"` to generate migration.

---

### Phase 2: Vapi Webhook Handler & Tool Execution Layer

**Files to create:**
```
backend/app/api/__init__.py
backend/app/api/deps.py
backend/app/api/v1/__init__.py
backend/app/api/v1/webhook_vapi.py
backend/app/api/v1/customers.py
backend/app/api/v1/churn.py
backend/app/api/v1/analytics.py
backend/app/api/v1/stream.py
backend/app/services/__init__.py
backend/app/services/customer_service.py
backend/app/services/dispatch_service.py
backend/app/services/churn_service.py
backend/app/services/transcript_service.py
backend/app/services/tool_executor.py
backend/app/main.py
```

**`backend/app/api/v1/webhook_vapi.py`** (core webhook handler):
```python
import hmac
import hashlib
import json
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.services.tool_executor import ToolExecutor
from app.services.customer_service import CustomerService
from app.services.transcript_service import TranscriptService
from app.api.deps import get_tool_executor, get_transcript_service
import logging

router = APIRouter(prefix="/webhook/vapi", tags=["vapi"])
logger = logging.getLogger(__name__)

def verify_vapi_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """HMAC-SHA256 verification of Vapi webhook payloads."""
    expected = hmac.new(secret.encode(), request_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@router.post("")
async def handle_vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tool_executor: ToolExecutor = Depends(get_tool_executor),
    transcript_service: TranscriptService = Depends(get_transcript_service),
):
    settings = get_settings()
    body_bytes = await request.body()
    
    # Verify webhook authenticity
    sig = request.headers.get("x-vapi-signature", "")
    if not verify_vapi_signature(body_bytes, sig, settings.VAPI_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    payload = json.loads(body_bytes)
    message = payload.get("message", {})
    event_type = message.get("type")
    
    logger.info(f"Vapi event: {event_type} | call_id: {message.get('call', {}).get('id')}")
    
    if event_type == "tool-calls":
        # Claude has emitted tool calls — execute them and return results
        results = await tool_executor.execute_batch(message.get("toolCallList", []))
        return JSONResponse({"results": results})
    
    elif event_type == "call-start":
        # Enrich Vapi assistant context with customer data
        call_id = message["call"]["id"]
        phone = message["call"]["customer"]["number"]
        enrichment = await tool_executor.customer_service.get_call_context(phone, call_id)
        # Return system prompt injection for Vapi
        return JSONResponse({
            "assistant": {
                "firstMessage": enrichment["greeting"],
                "model": {
                    "systemPrompt": enrichment["system_prompt_injection"]
                }
            }
        })
    
    elif event_type == "call-end":
        # Process transcript asynchronously — do not block webhook response
        background_tasks.add_task(
            transcript_service.process_completed_call,
            call_data=message
        )
        return JSONResponse({"status": "accepted"})
    
    return JSONResponse({"status": "ok"})
```

**`backend/app/services/tool_executor.py`** (dispatches Claude tool calls):
```python
from typing import Any
import logging
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.churn_service import ChurnService
from app.rag.retriever import RAGRetriever

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "schedule_dispatch": "execute_schedule_dispatch",
    "query_churn_score": "execute_query_churn_score",
    "get_customer_info": "execute_get_customer_info",
    "get_equipment_info": "execute_get_equipment_info",
    "rag_knowledge_query": "execute_rag_query",
    "create_support_ticket": "execute_create_ticket",
}

class ToolExecutor:
    def __init__(
        self,
        customer_service: CustomerService,
        dispatch_service: DispatchService,
        churn_service: ChurnService,
        rag_retriever: RAGRetriever,
    ):
        self.customer_service = customer_service
        self.dispatch_service = dispatch_service
        self.churn_service = churn_service
        self.rag_retriever = rag_retriever

    async def execute_batch(self, tool_call_list: list[dict]) -> list[dict]:
        """Execute all tool calls from a single LLM turn concurrently."""
        import asyncio
        tasks = [self._execute_single(tc) for tc in tool_call_list]
        return await asyncio.gather(*tasks)

    async def _execute_single(self, tool_call: dict) -> dict:
        tool_name = tool_call["name"]
        tool_call_id = tool_call["id"]
        args = tool_call.get("arguments", {})
        
        handler_name = TOOL_REGISTRY.get(tool_name)
        if not handler_name:
            return {"toolCallId": tool_call_id, "result": '{"error": "Unknown tool"}'}
        
        try:
            handler = getattr(self, handler_name)
            result = await handler(**args)
            return {"toolCallId": tool_call_id, "result": result}
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return {"toolCallId": tool_call_id, "result": f'{{"error": "{str(e)}"}}'}

    async def execute_schedule_dispatch(self, customer_id: str, issue_type: str,
                                         priority: str, preferred_window: str,
                                         issue_description: str, **kwargs) -> str:
        import json
        result = await self.dispatch_service.create_job(
            customer_id=customer_id,
            issue_type=issue_type,
            priority=priority,
            preferred_window=preferred_window,
            issue_description=issue_description,
            churn_context=kwargs.get("churn_risk_context"),
        )
        return json.dumps(result)

    async def execute_query_churn_score(self, customer_id: str) -> str:
        import json
        score = await self.churn_service.get_latest_score(customer_id)
        return json.dumps(score)

    async def execute_rag_query(self, query: str, **kwargs) -> str:
        import json
        chunks = await self.rag_retriever.retrieve(
            query=query,
            namespace=kwargs.get("namespace"),
            top_k=kwargs.get("top_k", 5),
            filter_model=kwargs.get("equipment_model"),
        )
        return json.dumps({"retrieved_context": chunks})
    
    # Implement remaining handlers: execute_get_customer_info, execute_get_equipment_info,
    # execute_create_ticket following the same async pattern.
```

---

### Phase 3: RAG Pipeline Integration

**Files to create:**
```
backend/app/rag/__init__.py
backend/app/rag/embedder.py
backend/app/rag/retriever.py
backend/app/rag/indexer.py
backend/app/rag/chunker.py
scripts/index_knowledge_base.py
data/knowledge/faqs/           (directory for FAQ markdown files)
data/knowledge/manuals/        (directory for equipment manual PDFs)
```

**`backend/app/rag/retriever.py`:**
```python
from pinecone import Pinecone
from openai import AsyncOpenAI
from app.core.config import get_settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class RAGRetriever:
    def __init__(self):
        settings = get_settings()
        self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index = self.pc.Index(settings.PINECONE_INDEX_NAME)
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dim = 1536

    async def embed_query(self, text: str) -> list[float]:
        response = await self.openai.embeddings.create(
            input=text,
            model=self.embedding_model
        )
        return response.data[0].embedding

    async def retrieve(
        self,
        query: str,
        namespace: Optional[str] = None,
        top_k: int = 5,
        filter_model: Optional[str] = None,
    ) -> list[dict]:
        vector = await self.embed_query(query)
        
        pinecone_filter = {}
        if filter_model:
            pinecone_filter["equipment_model"] = {"$eq": filter_model}
        
        query_kwargs = {
            "vector": vector,
            "top_k": top_k,
            "include_metadata": True,
        }
        if namespace:
            query_kwargs["namespace"] = namespace
        if pinecone_filter:
            query_kwargs["filter"] = pinecone_filter
        
        results = self.index.query(**query_kwargs)
        
        return [
            {
                "chunk_id": match.id,
                "text": match.metadata.get("text", ""),
                "source": match.metadata.get("source", ""),
                "similarity_score": match.score,
                "namespace": namespace or "default",
            }
            for match in results.matches
        ]
```

**`backend/app/rag/indexer.py`** (run at startup and nightly via Celery beat):
```python
# Indexes FAQ markdown files and equipment manuals into Pinecone
# Chunking strategy: RecursiveCharacterTextSplitter, chunk_size=512, overlap=64
# Each chunk stored with metadata: {source, namespace, equipment_model, chunk_index}
# Run: python scripts/index_knowledge_base.py --namespace faq_general --source data/knowledge/faqs/
```

---

### Phase 4: ML Feature Pipeline (Kafka + Celery)

**Files to create:**
```
backend/app/pipeline/__init__.py
backend/app/pipeline/celery_app.py
backend/app/pipeline/kafka_consumer.py
backend/app/pipeline/feature_extractor.py
backend/app/pipeline/sentiment_analyzer.py
backend/app/pipeline/tasks.py
backend/app/ml/__init__.py
backend/app/ml/churn_model.py
backend/app/ml/feature_builder.py
backend/app/ml/model_registry.py
ml/training/train_churn_model.py
ml/training/evaluate_model.py
ml/notebooks/01_eda.ipynb
ml/notebooks/02_feature_engineering.ipynb
ml/notebooks/03_model_training.ipynb
```

**`backend/app/pipeline/feature_extractor.py`** (post-call feature computation):
```python
from dataclasses import dataclass
from typing import Optional
import numpy as np
from app.pipeline.sentiment_analyzer import SentimentAnalyzer

@dataclass
class CallFeatureVector:
    """Extracted features from a single completed call transcript."""
    call_id: str
    customer_id: str
    
    # Sentiment
    sentiment_overall: float
    sentiment_trajectory: list[dict]   # [{minute: int, score: float}]
    sentiment_degradation_slope: float  # OLS slope
    anger_score: float
    frustration_score: float
    
    # Behavioral signals
    escalation_detected: bool
    recurrence_complaint_detected: bool  # "again", "third time", "still broken", etc.
    complaint_keywords: list[str]
    
    # Hesitation markers (extracted from word-level timestamps)
    pause_count: int                   # pauses > 1000ms between words
    avg_pause_ms: float
    filler_word_count: int             # um, uh, like, you know
    
    # Call metadata
    duration_seconds: int
    call_outcome: str
    rag_queries_count: int
    tool_calls_count: int


class FeatureExtractor:
    """
    Transforms Vapi transcript JSON into a CallFeatureVector.
    Input: transcript_json [{speaker, text, start_ms, end_ms, confidence}]
    """
    
    RECURRENCE_KEYWORDS = [
        "third time", "again", "still broken", "keeps happening",
        "same problem", "not fixed", "didn't fix", "back again",
        "second time", "every year", "every summer"
    ]
    
    COMPLAINT_KEYWORDS = [
        "frustrated", "disappointed", "unacceptable", "ridiculous",
        "cancel", "refund", "never again", "worst", "terrible",
        "hot", "broken", "not working", "failed", "useless"
    ]

    def __init__(self, sentiment_analyzer: SentimentAnalyzer):
        self.sentiment = sentiment_analyzer

    def extract(self, call_id: str, customer_id: str, transcript_json: list[dict],
                call_metadata: dict) -> CallFeatureVector:
        
        customer_utterances = [t for t in transcript_json if t["speaker"] == "customer"]
        full_text = " ".join([u["text"] for u in customer_utterances])
        
        # Sentiment analysis on full text and per-minute segments
        overall_sentiment = self.sentiment.analyze(full_text)
        trajectory = self._compute_sentiment_trajectory(customer_utterances)
        slope = self._compute_slope([p["score"] for p in trajectory])
        emotions = self.sentiment.classify_emotions(full_text)
        
        # Hesitation detection from word-level timestamps
        hesitation = self._extract_hesitation_markers(customer_utterances)
        
        # Keyword detection
        text_lower = full_text.lower()
        recurrence_detected = any(kw in text_lower for kw in self.RECURRENCE_KEYWORDS)
        found_complaints = [kw for kw in self.COMPLAINT_KEYWORDS if kw in text_lower]
        
        return CallFeatureVector(
            call_id=call_id,
            customer_id=customer_id,
            sentiment_overall=overall_sentiment["compound"],
            sentiment_trajectory=trajectory,
            sentiment_degradation_slope=slope,
            anger_score=emotions.get("anger", 0.0),
            frustration_score=emotions.get("frustration", 0.0),
            escalation_detected=call_metadata.get("escalation_detected", False),
            recurrence_complaint_detected=recurrence_detected,
            complaint_keywords=found_complaints,
            **hesitation,
            duration_seconds=call_metadata.get("duration_seconds", 0),
            call_outcome=call_metadata.get("call_outcome", "UNKNOWN"),
            rag_queries_count=call_metadata.get("rag_queries_issued", 0),
            tool_calls_count=len(call_metadata.get("tool_calls_log", [])),
        )

    def _compute_sentiment_trajectory(self, utterances: list[dict]) -> list[dict]:
        """Score sentiment for each 60-second segment of the call."""
        # Group utterances by minute, score each group, return [{minute, score}]
        ...

    def _compute_slope(self, scores: list[float]) -> float:
        """OLS slope of sentiment scores over time. Negative slope = degrading sentiment."""
        if len(scores) < 2:
            return 0.0
        x = np.arange(len(scores))
        slope, _ = np.polyfit(x, scores, 1)
        return float(slope)

    def _extract_hesitation_markers(self, utterances: list[dict]) -> dict:
        """
        Detect long pauses (>1000ms gap between consecutive words) and filler words.
        Requires word-level timestamps from Deepgram via Vapi transcript_json format.
        """
        FILLER_WORDS = {"um", "uh", "like", "you know", "erm", "hmm"}
        pause_count = 0
        pause_durations = []
        filler_count = 0
        
        for utterance in utterances:
            words = utterance.get("words", [])  # [{word, start_ms, end_ms}]
            for i in range(1, len(words)):
                gap = words[i]["start_ms"] - words[i-1]["end_ms"]
                if gap > 1000:
                    pause_count += 1
                    pause_durations.append(gap)
                if words[i]["word"].lower().strip(".,") in FILLER_WORDS:
                    filler_count += 1
        
        return {
            "pause_count": pause_count,
            "avg_pause_ms": float(np.mean(pause_durations)) if pause_durations else 0.0,
            "filler_word_count": filler_count,
        }
```

**`backend/app/pipeline/kafka_consumer.py`:**
```python
from kafka import KafkaConsumer
import json
import asyncio
import logging
from app.core.config import get_settings
from app.pipeline.tasks import process_call_features

logger = logging.getLogger(__name__)

def start_feature_consumer():
    """
    Long-running Kafka consumer for 'call.features' topic.
    Deserializes CallFeatureVector payloads and dispatches Celery scoring tasks.
    Runs in a dedicated thread; launched by the Celery worker on startup.
    """
    settings = get_settings()
    consumer = KafkaConsumer(
        settings.KAFKA_TOPIC_CALL_FEATURES,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="churn-feature-pipeline",
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
    )
    
    logger.info("Feature pipeline Kafka consumer started")
    for message in consumer:
        try:
            feature_payload = message.value
            # Dispatch to Celery for async feature store upsert + churn re-scoring
            process_call_features.delay(feature_payload)
            consumer.commit()
        except Exception as e:
            logger.error(f"Consumer error: {e}", exc_info=True)
```

**`backend/app/ml/churn_model.py`:**
```python
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)

class ChurnModelEnsemble:
    """
    Loads and runs the XGBoost + LightGBM ensemble for churn probability prediction.
    Artifacts loaded from MODEL_ARTIFACTS_PATH at startup.
    """
    
    FEATURE_ORDER = [
        # Must match exact order in CHURN_FEATURE_SCHEMA (§3.2)
        "escalation_frequency", "sentiment_degradation_slope", "avg_sentiment_score",
        "min_sentiment_score", "negative_call_ratio", "anger_emotion_ratio",
        "recurrence_complaint_count", "hesitation_marker_rate", "sentiment_std_dev",
        "sentiment_first_call", "sentiment_last_call", "avg_time_to_resolution_hours",
        "time_to_resolution_std_dev", "dispatch_cancellation_rate", "rescheduling_count",
        "open_ticket_age_days_avg", "open_ticket_count", "p1_p2_job_count",
        "same_issue_recurrence_count", "technician_change_count", "total_calls_window",
        "payment_delay_days_avg", "payment_failure_count", "days_since_last_positive_call",
        "days_since_last_service", "contract_days_until_renewal", "equipment_age_years",
        "warranty_expired", "customer_rating_avg_90d", "escalation_count",
        "sentiment_x_escalation", "resolution_x_recurrence", "payment_x_sentiment",
        "composite_risk_index",
    ]
    
    ENSEMBLE_WEIGHTS = {"xgboost": 0.55, "lightgbm": 0.35, "isolation_forest": 0.10}

    def __init__(self):
        settings = get_settings()
        artifacts_path = Path(settings.MODEL_ARTIFACTS_PATH)
        
        with open(artifacts_path / "xgb_churn_model.pkl", "rb") as f:
            self.xgb_model = pickle.load(f)
        
        with open(artifacts_path / "lgbm_churn_model.pkl", "rb") as f:
            self.lgbm_model = pickle.load(f)
        
        with open(artifacts_path / "isolation_forest.pkl", "rb") as f:
            self.isolation_forest = pickle.load(f)
        
        with open(artifacts_path / "feature_scaler.pkl", "rb") as f:
            self.scaler = pickle.load(f)
        
        with open(artifacts_path / "shap_explainer_xgb.pkl", "rb") as f:
            self.shap_explainer = pickle.load(f)
        
        logger.info(f"Churn model ensemble loaded from {artifacts_path}")

    def predict(self, feature_dict: dict) -> dict:
        """
        Args: feature_dict — keys matching FEATURE_ORDER
        Returns: {churn_probability, risk_tier, shap_contributions, model_version}
        """
        df = pd.DataFrame([feature_dict])[self.FEATURE_ORDER]
        df_scaled = self.scaler.transform(df)
        
        xgb_prob = self.xgb_model.predict_proba(df_scaled)[0][1]
        lgbm_prob = self.lgbm_model.predict_proba(df_scaled)[0][1]
        
        # Isolation Forest: anomaly score [-1, 1] normalized to [0, 1]
        iso_score = self.isolation_forest.score_samples(df_scaled)[0]
        iso_normalized = float(1 - (iso_score - (-0.5)) / (0.5 - (-0.5)))  # rough normalization
        iso_normalized = max(0.0, min(1.0, iso_normalized))
        
        ensemble_prob = (
            xgb_prob * self.ENSEMBLE_WEIGHTS["xgboost"] +
            lgbm_prob * self.ENSEMBLE_WEIGHTS["lightgbm"] +
            iso_normalized * self.ENSEMBLE_WEIGHTS["isolation_forest"]
        )
        ensemble_prob = float(max(0.0, min(1.0, ensemble_prob)))
        
        # SHAP for explainability (XGBoost model only)
        shap_values = self.shap_explainer(df_scaled)
        top_features = sorted(
            zip(self.FEATURE_ORDER, shap_values.values[0].tolist()),
            key=lambda x: abs(x[1]), reverse=True
        )[:5]
        
        risk_tier = self._score_to_tier(ensemble_prob)
        
        return {
            "churn_probability": round(ensemble_prob, 3),
            "risk_tier": risk_tier,
            "feature_contributions": [
                {"feature": f, "shap_value": round(v, 4), "direction": "INCREASES_RISK" if v > 0 else "DECREASES_RISK"}
                for f, v in top_features
            ],
            "model_version": "ensemble_v1.0.0",
        }

    @staticmethod
    def _score_to_tier(score: float) -> str:
        if score >= 0.80: return "CRITICAL"
        if score >= 0.60: return "HIGH"
        if score >= 0.35: return "MEDIUM"
        return "LOW"
```

**`ml/training/train_churn_model.py`** (executed offline to produce model artifacts):
```python
# Pipeline:
# 1. Load feature_store table from PostgreSQL (90-day windows)
# 2. Load ground truth labels: churned within 90 days of window_end
# 3. Train/val/test split (70/15/15, time-based to prevent leakage)
# 4. Fit StandardScaler on train set
# 5. Train XGBoost with Optuna hyperparameter search (50 trials, AUC-ROC objective)
# 6. Train LightGBM with Optuna hyperparameter search (50 trials)
# 7. Fit IsolationForest on train features
# 8. Calibrate probabilities using CalibratedClassifierCV (isotonic regression)
# 9. Evaluate ensemble on test set: AUC-ROC, AUC-PR, Brier Score, F1@0.5
# 10. Compute SHAP explainer for XGBoost
# 11. Serialize all artifacts to ml/artifacts/
# 12. Log metrics to MLflow (optional, recommend mlflow.set_tracking_uri())
```

---

### Phase 5: Analytics API & Server-Sent Events

**Files to create:**
```
backend/app/api/v1/analytics.py
backend/app/api/v1/stream.py
backend/app/services/analytics_service.py
```

**`backend/app/api/v1/stream.py`** (SSE endpoint):
```python
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.pipeline.event_bus import EventBus  # Redis pub/sub wrapper

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])

@router.get("/churn-events")
async def stream_churn_events():
    """
    Server-Sent Events endpoint for the real-time dashboard feed.
    Subscribes to Redis pub/sub channels: 'call.active', 'churn.intervention', 'batch.complete'
    Frontend connects once; events stream until disconnection.
    """
    async def event_generator():
        async with EventBus() as bus:
            async for event in bus.subscribe(["call.active", "churn.intervention", "batch.complete"]):
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)  # yield control
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
```

---

### Phase 6: Next.js Frontend Dashboard

**Files to create:**
```
frontend/app/layout.tsx
frontend/app/page.tsx                              (redirect to /dashboard)
frontend/app/dashboard/page.tsx                    (main KPI overview)
frontend/app/dashboard/customers/page.tsx          (customer list + search)
frontend/app/dashboard/customers/[id]/page.tsx     (customer churn timeline)
frontend/app/dashboard/analytics/page.tsx          (Saved by AI metrics)
frontend/components/ChurnRiskDonut.tsx
frontend/components/ChurnTimelineChart.tsx
frontend/components/CohortHeatmap.tsx
frontend/components/SavedByAIMetrics.tsx
frontend/components/LiveCallFeed.tsx
frontend/components/RiskBadge.tsx
frontend/lib/api.ts                                (typed API client)
frontend/lib/sse.ts                                (SSE hook)
frontend/types/churn.ts                            (TypeScript type definitions)
frontend/types/customer.ts
```

**`frontend/types/churn.ts`** — all types matching §5.1 exactly:
```typescript
export type RiskTier = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export const RISK_COLORS: Record<RiskTier, string> = {
  LOW: "#22c55e",
  MEDIUM: "#f59e0b",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};

export interface ChurnScore {
  churn_probability: number;
  risk_tier: RiskTier;
  feature_contributions: FeatureContribution[];
  model_version: string;
  score_age_minutes: number;
  last_scored_at: string;
}

export interface FeatureContribution {
  feature: string;
  shap_value: number;
  direction: "INCREASES_RISK" | "DECREASES_RISK";
}

export interface ChurnTimelinePoint {
  timestamp: string;
  churn_probability: number;
  risk_tier: RiskTier;
  event?: {
    type: "CALL_START" | "DISPATCH_CREATED" | "INTERVENTION_APPLIED" | "TICKET_RESOLVED" | "CHURNED";
    label: string;
    call_id?: string;
  };
}

export interface ChurnTimelineResponse {
  customer_id: string;
  customer_name: string;
  data_points: ChurnTimelinePoint[];
  current_score: number;
  score_90d_ago: number;
  net_change: number;
  interventions_count: number;
  saved_by_ai: boolean;
}

export interface SavedByAIResponse {
  period_start: string;
  period_end: string;
  total_high_risk_calls: number;
  successful_interventions: number;
  intervention_success_rate: number;
  estimated_arr_retained_usd: number;
  avg_score_reduction: number;
  monthly_trend: {
    month: string;
    interventions: number;
    arr_retained_usd: number;
    success_rate: number;
  }[];
}

export interface SSEChurnEvent {
  event_type: "CALL_ACTIVE" | "INTERVENTION_COMPLETE" | "BATCH_SCORE_COMPLETE";
  call_id?: string;
  customer_id?: string;
  customer_name?: string;
  churn_risk_tier?: RiskTier;
  churn_probability?: number;
  score_before?: number;
  score_after?: number;
  delta?: number;
  saved_by_ai?: boolean;
  intervention_type?: string;
  timestamp: string;
}
```

**`frontend/components/ChurnTimelineChart.tsx`:**
```tsx
"use client";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
         ReferenceLine, ReferenceDot, ResponsiveContainer, Label } from "recharts";
import { ChurnTimelinePoint, RISK_COLORS } from "@/types/churn";
import { format, parseISO } from "date-fns";

interface Props {
  data: ChurnTimelinePoint[];
  savedByAI: boolean;
}

export function ChurnTimelineChart({ data, savedByAI }: Props) {
  const interventionPoints = data.filter(d => d.event?.type === "INTERVENTION_APPLIED");
  
  return (
    <div className="relative">
      {savedByAI && (
        <div className="absolute top-2 right-2 z-10 bg-green-100 text-green-800 
                        text-xs font-bold px-2 py-1 rounded-full border border-green-300">
          ✓ SAVED BY AI
        </div>
      )}
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(v) => format(parseISO(v), "MMM d")}
            tick={{ fontSize: 11 }}
          />
          <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number) => [`${(value * 100).toFixed(1)}%`, "Churn Probability"]}
            labelFormatter={(label) => format(parseISO(label as string), "MMM d, yyyy HH:mm")}
          />
          {/* Risk tier threshold lines */}
          <ReferenceLine y={0.60} stroke={RISK_COLORS.HIGH} strokeDasharray="4 4">
            <Label value="HIGH" position="right" fontSize={10} fill={RISK_COLORS.HIGH} />
          </ReferenceLine>
          <ReferenceLine y={0.80} stroke={RISK_COLORS.CRITICAL} strokeDasharray="4 4">
            <Label value="CRITICAL" position="right" fontSize={10} fill={RISK_COLORS.CRITICAL} />
          </ReferenceLine>
          {/* Intervention markers */}
          {interventionPoints.map((point, i) => (
            <ReferenceDot
              key={i}
              x={point.timestamp}
              y={point.churn_probability}
              r={6}
              fill="#3b82f6"
              stroke="white"
              strokeWidth={2}
              label={{ value: "⚡", position: "top", fontSize: 14 }}
            />
          ))}
          <Line
            type="monotone"
            dataKey="churn_probability"
            stroke="#6366f1"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

**`frontend/lib/sse.ts`** (React hook for SSE):
```typescript
import { useEffect, useState, useRef } from "react";
import { SSEChurnEvent } from "@/types/churn";

export function useChurnEventStream(apiBase: string) {
  const [events, setEvents] = useState<SSEChurnEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(`${apiBase}/api/v1/stream/churn-events`);
    esRef.current = es;
    
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    
    es.onmessage = (e: MessageEvent) => {
      const event: SSEChurnEvent = JSON.parse(e.data);
      setEvents(prev => [event, ...prev].slice(0, 50)); // keep last 50 events
    };
    
    return () => { es.close(); setConnected(false); };
  }, [apiBase]);

  return { events, connected };
}
```

---

### Phase 7: Testing & Observability

**Files to create:**
```
backend/tests/test_webhook_vapi.py
backend/tests/test_tool_executor.py
backend/tests/test_feature_extractor.py
backend/tests/test_churn_model.py
backend/tests/test_rag_retriever.py
backend/tests/conftest.py
backend/tests/fixtures/sample_vapi_transcript.json
backend/tests/fixtures/sample_feature_vector.json
```

**`backend/tests/test_feature_extractor.py`:**
```python
import pytest
from app.pipeline.feature_extractor import FeatureExtractor
from app.pipeline.sentiment_analyzer import SentimentAnalyzer

@pytest.fixture
def extractor():
    return FeatureExtractor(SentimentAnalyzer())

def test_recurrence_detection(extractor, sample_transcript):
    """Verifies that 'third time' triggers recurrence_complaint_detected=True."""
    transcript = [{"speaker": "customer", "text": "This is the third time this has happened.", "words": []}]
    vector = extractor.extract("call_1", "cust_1", transcript, {"duration_seconds": 60})
    assert vector.recurrence_complaint_detected is True

def test_sentiment_slope_negative_call(extractor):
    """Sentiment degradation slope must be negative for a call that starts neutral and ends angry."""
    utterances = [
        {"speaker": "customer", "text": "Hi, I guess my AC is making a noise.", "words": []},
        {"speaker": "customer", "text": "It's been a week, nobody came, I'm very frustrated.", "words": []},
        {"speaker": "customer", "text": "This is unacceptable, I want to cancel my contract.", "words": []},
    ]
    vector = extractor.extract("call_2", "cust_2", utterances, {"duration_seconds": 180})
    assert vector.sentiment_degradation_slope < 0, "Slope should be negative for degrading sentiment"

def test_hesitation_marker_extraction(extractor):
    """Detects filler words in transcript."""
    utterances = [{"speaker": "customer", "text": "Um, yeah, uh, I don't know, like, it just stopped.", "words": [
        {"word": "Um", "start_ms": 0, "end_ms": 200},
        {"word": "yeah", "start_ms": 201, "end_ms": 400},
        {"word": "uh", "start_ms": 401, "end_ms": 600},
    ]}]
    vector = extractor.extract("call_3", "cust_3", utterances, {"duration_seconds": 30})
    assert vector.filler_word_count >= 2
```

**Observability stack (add to `docker-compose.yml`):**
```yaml
prometheus:
  image: prom/prometheus:v2.52.0
  volumes: ["./infra/prometheus.yml:/etc/prometheus/prometheus.yml"]
  ports: ["9090:9090"]

grafana:
  image: grafana/grafana:10.4.2
  ports: ["3001:3000"]
  volumes: ["grafana_data:/var/lib/grafana"]
  environment:
    GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
```

**Key metrics to instrument (FastAPI + Prometheus):**
```python
# Add to backend/app/core/metrics.py using prometheus-fastapi-instrumentator
from prometheus_client import Counter, Histogram, Gauge

vapi_webhook_total = Counter("vapi_webhook_total", "Total Vapi webhook events", ["event_type"])
tool_execution_latency = Histogram("tool_execution_latency_seconds", "Tool execution latency", ["tool_name"])
churn_scoring_latency = Histogram("churn_scoring_latency_seconds", "ML model scoring latency")
high_risk_accounts_gauge = Gauge("high_risk_accounts_total", "Current HIGH+CRITICAL accounts")
saved_by_ai_counter = Counter("saved_by_ai_total", "AI-attributed retention interventions")
rag_retrieval_latency = Histogram("rag_retrieval_latency_seconds", "Pinecone query latency")
```

---

### Phase 8: Production Deployment Checklist

**Files to create:**
```
infra/k8s/namespace.yaml
infra/k8s/backend-deployment.yaml
infra/k8s/celery-deployment.yaml
infra/k8s/frontend-deployment.yaml
infra/k8s/services.yaml
infra/k8s/ingress.yaml
infra/k8s/secrets.yaml.template
infra/terraform/main.tf                 (optional: AWS EKS + RDS + MSK)
.github/workflows/ci.yml
.github/workflows/deploy.yml
```

**Pre-production gate criteria:**
- [ ] All Phase 7 tests pass with >90% coverage on services/ and pipeline/
- [ ] Churn model AUC-ROC ≥ 0.78 on held-out test set (logged to MLflow)
- [ ] Vapi webhook p99 latency < 200ms (tool execution excluded)
- [ ] RAG retrieval p99 latency < 800ms
- [ ] SSE stream stable for 1h+ under load (50 concurrent connections)
- [ ] Feature pipeline processes call.features topic with < 30s end-to-end lag
- [ ] Churn re-scoring completes within 6-hour SLA on 500-account corpus
- [ ] Grafana dashboard live with all 8 key metrics instrumentated
- [ ] Database migrations idempotent and tested against production schema clone
- [ ] Secrets management via AWS Secrets Manager or Vault (no .env in production)

---

*End of HVAC-Intelligence (Project Aero) Technical Specification*
*Document version: 1.0.0 | Generated: 2025-05-30 | Target: Cursor autonomous build*
