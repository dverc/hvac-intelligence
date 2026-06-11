# HVAC Intelligence (Project Aero)

## Description

Multi-tenant AI voice agent and churn prediction platform for field service businesses.

## Supported Trades

HVAC, plumbing, electrical, roofing, restoration, appliance repair, garage doors, locksmith, pest control.

## Tech Stack

FastAPI, PostgreSQL, Redis, Celery, Next.js 14, Vapi, Pinecone, Anthropic Claude, Google Calendar, Jobber.

## Key Features

- Inbound AI voice agent (**12 tools in Vapi dashboard**; `transfer_call` and `check_service_area` built in code, pending Vapi setup)
- Churn prediction
- Multi-tenant isolation
- CSV import
- Google Drive sync
- Google Calendar bidirectional sync
- Jobber bidirectional sync
- Two onboarding flows: self-service `/dashboard/onboarding` (6 steps) and admin `/dashboard/admin/onboarding/[org_id]` (5 steps)

## Architecture

Monorepo with `backend/` and `frontend/`, Docker Compose for local dev, GitHub Actions CI.

## Current Phase

Phase 10 complete (all dashboard routes, dual onboarding wizards, admin UI, customer portal).

## Ground truth for agents

See [`docs/CURSOR_PROJECT_NOTES.md`](./CURSOR_PROJECT_NOTES.md) for verified DB state, API paths (`/api/v1/scheduling/*`), auth (`JWT_SECRET_KEY`, dual JWT + API key), Celery queue bug, and live org/user IDs.
