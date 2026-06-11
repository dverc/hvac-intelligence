# Cursor Project Notes — Ground Truth (verified 2026-06-11)

Authoritative reference for agents and developers. Cross-check this file before generating ops commands, API paths, or auth assumptions.

---

## Users & login

- **Primary key column:** `users.id` (UUID) — **not** `user_id`.
- **Confirmed admin user** (created via register API, **not** seeded by migrations):

| Field | Value |
|-------|-------|
| `id` | `0b5a31f1-0272-4efc-b086-a6438d8edf4b` |
| `email` | `daniel@hvacintelligence.com` |
| `role` | `admin` |
| `created_at` | 2026-06-09 |

- **After a DB wipe:** recreate login with `POST /api/v1/auth/register` and header `X-API-Key: $DASHBOARD_API_KEY` (register requires API key).
- **Admin check:** `current_user.get("role") != "admin"` only — **no** `is_superuser` field on `User` model.

---

## Organizations (live DB)

| org_id | org_name | Origin | created |
|--------|----------|--------|---------|
| `00000000-0000-4000-8000-000000000001` | HVAC Intelligence Demo | Seeded in migration 005 | 2026-06-02 |
| `bff79a29-2754-48da-b9f7-7b4ccaa8eb08` | **Bob** (not "Bob's Plumbing") | Admin onboarding wizard | 2026-06-04 |

---

## Seed customer (Daniel V)

| Field | Value |
|-------|-------|
| `customer_id` | `18ea568c-5db5-4a41-ab1d-18314a9d54e4` |
| `full_name` | Daniel V |
| `phone_primary` | `+19493313190` |
| `org_id` | `00000000-0000-4000-8000-000000000001` |

---

## Docker / infrastructure (confirmed `docker compose ps`)

Six containers typically **Up**: `postgres`, `redis`, `celery-worker`, `celery-beat`, `kafka`, `zookeeper`.

- Postgres image: **`pgvector/pgvector:pg16`** (not plain `postgres`).
- Kafka + Zookeeper have been running continuously in local dev (4+ days as of 2026-06-11).

---

## Celery queue bug (known)

`docker-compose.yml` runs:

```text
celery -A app.pipeline.celery_app worker -Q features,scoring -c 4
```

All **8 beat-scheduled tasks** use the **default `celery` queue**. The worker does **not** consume that queue, so these do **not** run automatically until fixed:

- `execute_outbound_campaign`
- `sync_jobber_data`
- `sync_google_calendars`
- `batch_rescore_customers`
- `check_and_launch_campaigns`
- `sync_technician_schedules`
- `send_weekly_client_reports`
- `check_model_drift_and_retrain`
- `sync_google_drive_folders`

**Fix:** change worker command to `-Q celery,features,scoring` in `docker-compose.yml`.

Beat schedule reference: `backend/app/pipeline/celery_app.py`.

---

## Vapi tools

- **12 tools** are configured and linked in the **Vapi dashboard** (as of 2026-06-04).
- **2 additional tools** exist in code (`backend/app/services/tool_executor.py`) but are **pending Vapi dashboard setup** (not missing from codebase):
  - `transfer_call`
  - `check_service_area`
- Schemas for pending tools: `docs/vapi_tool_schemas.md`.

---

## Onboarding wizards (two separate flows)

| Route | Steps | Purpose |
|-------|-------|---------|
| `/dashboard/onboarding` | 6: Business Details → Import Customers → Import Equipment → Knowledge Base → Configure Agent → Complete | Self-service client onboarding |
| `/dashboard/admin/onboarding/[org_id]` | 5-step admin wizard | Admin-provisioned tenants |

Both are functional. API for self-service provision: `POST /api/v1/onboarding/provision`.

---

## Dispatch / scheduling API

- **File:** `backend/app/api/v1/scheduling.py` — there is **no** `dispatch.py`.
- **URL prefix:** `/api/v1/scheduling/*` — **not** `/api/v1/dispatch/*`.
- **No** `POST /api/v1/scheduling/jobs` — jobs are created only via the Vapi `schedule_dispatch` tool.
- List jobs: `GET /api/v1/scheduling/jobs?date_from=…&date_to=…`

---

## Auth & API keys

- Protected `/api/v1/*` routes require **both**:
  1. `Authorization: Bearer <JWT>` (dashboard pages)
  2. `X-API-Key: $DASHBOARD_API_KEY` (must match `NEXT_PUBLIC_API_KEY` in frontend)
- **Exceptions** (no dashboard API key): `/api/v1/portal/*`, `/api/v1/stream/*`, `/webhook/vapi`, OAuth callbacks.
- JWT signing env var: **`JWT_SECRET_KEY`** — do **not** use `SECRET_KEY`.

---

## Environment variables

| Correct | Wrong |
|---------|-------|
| `JWT_SECRET_KEY` | `SECRET_KEY` |

Applies to `.env`, `.env.example`, and GitHub Actions CI (`JWT_SECRET_KEY: test-jwt-secret-for-ci`).

---

## Frontend routes

| Correct | Does not exist |
|---------|----------------|
| `/dashboard/health` | `/dashboard/system-health` |

---

## Outbound consent API

| Action | Method & path |
|--------|----------------|
| Record consent | `POST /api/v1/outbound/consent/{customer_id}` (UUID, not phone) |
| Revoke consent | `DELETE /api/v1/outbound/consent/{customer_id}` |
| Check consent | `GET /api/v1/outbound/consent/{customer_id}` |
| Preview eligible | `GET /api/v1/outbound/campaigns/preview-eligible` (query params; not `/{id}/eligible`) |

---

## Portal timezone (incomplete fix)

- **Backend:** reads timezone from `OrgSettings` ✅ (`portal_service.py`)
- **Frontend:** `frontend/lib/portal-format.ts` still hardcodes `America/Los_Angeles` ❌ — display bug for non-Pacific orgs until frontend is updated.

---

## Live call history

| Date | Notes |
|------|-------|
| 2026-06-03 | Most recent fully successful documented call; cost **$0.58** |
| Later | Call `019e911d-4d3d` ($0.1232) — stalled; phone lookup without `+1` |
| Later | Call `019e911e-9355` ($0.0018) — near-immediate hangup |
| Dashboard | **21 total calls** (cumulative test calls) |

**Pending test:** book Marcus at 2–4 PM and verify Google Calendar shows correct PDT (timezone fix validation).

---

## Migrations

- Head: `029_org_settings_constraints` (29 migrations total).
- Alembic version in old checklists may show `014` — always run `alembic current` after upgrades.

---

## Related docs

| File | Purpose |
|------|---------|
| `docs/RUNBOOK.md` | Startup, Celery, Kafka, operations |
| `docs/MANUAL_VERIFICATION_CHECKLIST.md` | Manual QA steps |
| `docs/vapi_tool_schemas.md` | Vapi tool JSON (incl. pending tools) |
| `docs/PRE_PRODUCTION_CHECKLIST.md` | Production gates |
