# HVAC Intelligence (Project Aero)

## Description

Multi-tenant AI voice agent and churn prediction platform for field service businesses.

## Supported Trades

HVAC, plumbing, electrical, roofing, restoration, appliance repair, garage doors, locksmith, pest control.

## Tech Stack

FastAPI, PostgreSQL, Redis, Celery, Next.js 14, Vapi, Pinecone, Anthropic Claude, Google Calendar, Jobber.

## Key Features

- Inbound AI voice agent (12 tools)
- Churn prediction
- Multi-tenant isolation
- CSV import
- Google Drive sync
- Google Calendar bidirectional sync
- Jobber bidirectional sync

## Architecture

Monorepo with `backend/` and `frontend/`, Docker Compose for local dev, GitHub Actions CI.

## Current Phase

Phase 10 complete (all 10 dashboard routes, onboarding wizard, admin UI).
