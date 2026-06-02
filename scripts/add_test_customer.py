#!/usr/bin/env python3
"""Insert a single HIGH-risk test customer for Vapi webhook / local dev demos."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.config import get_settings  # noqa: E402
from app.models.churn_score import ChurnScore  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.equipment import Equipment  # noqa: E402
from app.services.customer_service import normalize_phone  # noqa: E402


def sync_database_url() -> str:
    url = get_settings().DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url


def find_by_phone(session: Session, phone: str) -> Customer | None:
    normalized = normalize_phone(phone)
    digits = "".join(c for c in normalized if c.isdigit())
    stmt = select(Customer).where(
        or_(
            Customer.phone_primary == phone,
            Customer.phone_primary == normalized,
            Customer.phone_secondary == phone,
            Customer.phone_secondary == normalized,
        )
    )
    for row in session.execute(stmt).scalars().all():
        row_digits = "".join(c for c in row.phone_primary if c.isdigit())
        if row_digits == digits:
            return row
    return None


def risk_tier_for_score(score: float) -> str:
    if score >= 0.80:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def add_test_customer(session: Session, phone: str, name: str, churn_score: float) -> Customer:
    existing = find_by_phone(session, phone)
    if existing is not None:
        print(f"Customer already exists: customer_id={existing.customer_id} phone={existing.phone_primary}")
        return existing

    normalized_phone = normalize_phone(phone)
    today = date.today()
    customer_since = today - timedelta(days=365 * 2)
    install_date = today - timedelta(days=365 * 7)
    tier = risk_tier_for_score(churn_score)
    prob = Decimal(str(round(churn_score, 3)))

    customer = Customer(
        external_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        full_name=name,
        phone_primary=normalized_phone,
        email=f"{name.split()[0].lower()}.test@hvacops.local",
        address_line1="1 Demo Lane",
        city="Newport Beach",
        state="CA",
        zip="92660",
        account_status="ACTIVE",
        customer_since=customer_since,
        contract_type="ANNUAL_MAINTENANCE",
        contract_value_usd=Decimal("1200.00"),
        payment_method="CARD",
        metadata_={"churn_tier": tier, "churn_score": churn_score},
    )
    session.add(customer)
    session.flush()

    equipment = Equipment(
        customer_id=customer.customer_id,
        make="Carrier",
        model="Infinity 24ANB6",
        serial_number=f"CAR-{uuid.uuid4().hex[:10].upper()}",
        equipment_type="AC_UNIT",
        install_date=install_date,
        last_service_date=today - timedelta(days=180),
        service_count=4,
        age_years=Decimal("7.00"),
        known_issues=["intermittent_cooling"],
    )
    session.add(equipment)

    churn_row = ChurnScore(
        entity_type="CUSTOMER",
        entity_id=customer.customer_id,
        churn_probability=prob,
        risk_tier=tier,
        feature_contributions=[
            {
                "feature": "escalation_frequency",
                "shap_value": 0.15,
                "direction": "INCREASES_RISK",
            }
        ],
        model_version="test_seed",
        scoring_trigger="TEST_CUSTOMER_SCRIPT",
        prediction_horizon_days=90,
    )
    session.add(churn_row)
    session.flush()

    return customer


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a single test customer for Vapi demos")
    parser.add_argument("--phone", required=True, help="E.164 phone, e.g. +19493313190")
    parser.add_argument("--name", required=True, help="Customer full name")
    parser.add_argument(
        "--churn-score",
        type=float,
        default=0.85,
        help="Churn probability for metadata and churn_scores row (default: 0.85)",
    )
    args = parser.parse_args()

    engine = create_engine(sync_database_url())
    with Session(engine) as session:
        customer = add_test_customer(session, args.phone, args.name, args.churn_score)
        session.commit()
        print(
            f"Success: customer_id={customer.customer_id} "
            f"phone={customer.phone_primary} name={customer.full_name}"
        )


if __name__ == "__main__":
    main()
