"""Shared constants for tenant isolation.

SEED_ORG_ID is the single deterministic organization used to backfill
existing single-tenant rows (migrations 005/006) and as the safe default
tenant for local/dev. It is referenced by migrations, seed code, and tests;
never change this value once data has been backfilled against it.
"""

from __future__ import annotations

import uuid

SEED_ORG_ID: uuid.UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")

# String form for SQL server_default / raw migration inserts.
SEED_ORG_ID_STR: str = str(SEED_ORG_ID)

ALLOWED_INDUSTRIES: tuple[str, ...] = (
    "hvac",
    "plumbing",
    "electrical",
    "isp",
    "appliance_repair",
    "locksmith",
    "pest_control",
    "other",
)

ALLOWED_PLAN_TIERS: tuple[str, ...] = (
    "starter",
    "professional",
    "enterprise",
)
