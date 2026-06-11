# HVAC Intelligence Dashboard (Phase 6)

Next.js 14 App Router dashboard with Tremor v3 and Recharts.

## Dependencies (pinned)

| Package | Version |
|---------|---------|
| next | 14.2.18 |
| react | 18.3.1 |
| @tremor/react | **3.18.7** (v3 — import from `@tremor/react`) |
| recharts | 2.13.3 |
| date-fns | 3.6.0 |
| tailwindcss | 3.4.15 |

## Setup

```bash
cd frontend
cp .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

Open http://localhost:3000 (redirects to `/dashboard`).

Set `NEXT_PUBLIC_API_KEY` to match backend `DASHBOARD_API_KEY`. System health page: `/dashboard/health` (not `/system-health`). See `docs/CURSOR_PROJECT_NOTES.md` for auth and portal timezone notes.

## Tremor v3 note

All Tremor imports use **`@tremor/react`** (not `@tremor/ui` or v2 paths). Client components that use Tremor charts must include `"use client"` at the top of the file.
