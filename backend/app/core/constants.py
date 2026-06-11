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

# Churn risk thresholds (unified scoring and dashboard tiers)
CHURN_CRITICAL_THRESHOLD: float = 0.85
CHURN_HIGH_THRESHOLD: float = 0.65
CHURN_MEDIUM_THRESHOLD: float = 0.40

# Account lockout (login brute-force protection)
MAX_FAILED_LOGINS: int = 5
LOCKOUT_MINUTES: int = 15

# ML pipeline quality gates
MIN_TRAINING_SAMPLES: int = 10
MODEL_QUALITY_THRESHOLD: float = 0.55

# Auth rate limits (SlowAPI format strings)
LOGIN_RATE_LIMIT: str = "5/minute"
FORGOT_PASSWORD_RATE_LIMIT: str = "5/minute"

DEFAULT_ORG_TIMEZONE: str = "America/Los_Angeles"

# Federal TCPA calling window (customer local time) — non-negotiable
TCPA_CALLING_HOURS_START: int = 8
TCPA_CALLING_HOURS_END: int = 21

# Outbound campaign defaults (org may narrow within TCPA window)
OUTBOUND_DEFAULT_CHURN_THRESHOLD: float = 0.75
OUTBOUND_DEFAULT_MAX_ATTEMPTS: int = 2
OUTBOUND_DEFAULT_CALLING_HOURS_START: int = 9
OUTBOUND_DEFAULT_CALLING_HOURS_END: int = 18
OUTBOUND_ATTEMPT_LOOKBACK_DAYS: int = 30

DISCLOSURE_STYLE_FRIENDLY: str = "FRIENDLY"
DISCLOSURE_STYLE_FORMAL: str = "FORMAL"

CONSENT_TYPE_OUTBOUND_CALL: str = "OUTBOUND_CALL"
CONSENT_TYPE_SMS: str = "SMS"
CONSENT_TYPE_RECORDING: str = "RECORDING"
