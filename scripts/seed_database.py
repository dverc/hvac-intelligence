#!/usr/bin/env python3
"""Seed PostgreSQL with realistic HVAC operations dummy data for local development."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.config import get_settings  # noqa: E402
from app.models.call_transcript import CallTranscript  # noqa: E402
from app.models.churn_score import ChurnScore  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.equipment import Equipment  # noqa: E402
from app.models.technician import Technician  # noqa: E402


def sync_database_url() -> str:
    url = get_settings().DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url


def age_years_from_date(ref: date) -> Decimal:
    today = date.today()
    years = today.year - ref.year - ((today.month, today.day) < (ref.month, ref.day))
    return Decimal(str(years))


def seed_technicians(session: Session) -> list[Technician]:
    techs = [
        Technician(
            employee_number="TECH-1001",
            full_name="Marcus Thompson",
            phone="+15551234001",
            email="marcus.t@hvacops.local",
            employment_status="ACTIVE",
            hire_date=date(2016, 4, 12),
            tenure_years=age_years_from_date(date(2016, 4, 12)),
            certifications=["EPA_608", "NATE_AC", "NATE_HEAT_PUMP"],
            service_zones=["90210", "90211", "90024"],
            avg_customer_rating=Decimal("4.82"),
            jobs_completed_90d=118,
            complaints_received_90d=2,
            churn_risk_score=Decimal("0.120"),
            churn_risk_tier="LOW",
        ),
        Technician(
            employee_number="TECH-1002",
            full_name="Elena Vasquez",
            phone="+15551234002",
            email="elena.v@hvacops.local",
            employment_status="ACTIVE",
            hire_date=date(2021, 9, 1),
            tenure_years=age_years_from_date(date(2021, 9, 1)),
            certifications=["EPA_608", "NATE_AC"],
            service_zones=["90045", "90094", "90230"],
            avg_customer_rating=Decimal("4.65"),
            jobs_completed_90d=96,
            complaints_received_90d=5,
            churn_risk_score=Decimal("0.380"),
            churn_risk_tier="MEDIUM",
        ),
    ]
    session.add_all(techs)
    session.flush()
    return techs


def seed_customers(session: Session, techs: list[Technician]) -> list[Customer]:
    profiles = [
        ("Sarah Mitchell", "+15552001001", "ACTIVE", "ANNUAL_MAINTENANCE", 2400.00, "HIGH"),
        ("Robert Kim", "+15552001002", "ACTIVE", "RESIDENTIAL_OTC", 850.00, "CRITICAL"),
        ("Jennifer Lopez", "+15552001003", "ACTIVE", "COMMERCIAL_SLA", 12000.00, "MEDIUM"),
        ("David Chen", "+15552001004", "ACTIVE", "ANNUAL_MAINTENANCE", 1800.00, "LOW"),
        ("Amanda Foster", "+15552001005", "ACTIVE", "RESIDENTIAL_OTC", 620.00, "HIGH"),
        ("Michael O'Brien", "+15552001006", "PROSPECT", "RESIDENTIAL_OTC", None, "LOW"),
        ("Lisa Patel", "+15552001007", "ACTIVE", "COMMERCIAL_SLA", 9800.00, "MEDIUM"),
        ("James Wilson", "+15552001008", "SUSPENDED", "ANNUAL_MAINTENANCE", 2100.00, "CRITICAL"),
        ("Emily Nguyen", "+15552001009", "ACTIVE", "RESIDENTIAL_OTC", 740.00, "LOW"),
        ("Christopher Hayes", "+15552001010", "ACTIVE", "ANNUAL_MAINTENANCE", 1950.00, "HIGH"),
    ]
    customers: list[Customer] = []
    for idx, (name, phone, status, contract, value, tier) in enumerate(profiles):
        customers.append(
            Customer(
                external_id=f"CRM-{1000 + idx}",
                full_name=name,
                phone_primary=phone,
                email=f"{name.split()[0].lower()}.{name.split()[-1].lower()}@example.com",
                address_line1=f"{120 + idx} Oak Street",
                city="Los Angeles",
                state="CA",
                zip="900" + str(10 + idx),
                account_status=status,
                customer_since=date(2018 + (idx % 5), 1, 15),
                contract_type=contract,
                contract_value_usd=Decimal(str(value)) if value else None,
                payment_method="ACH" if idx % 2 == 0 else "CARD",
                preferred_tech_id=techs[idx % 2].technician_id,
                notes="Priority market account" if tier in {"HIGH", "CRITICAL"} else None,
                metadata_={"churn_tier": tier, "segment": "residential" if "RESIDENTIAL" in contract else "commercial"},
            )
        )
    session.add_all(customers)
    session.flush()
    return customers


def seed_call_transcripts(
    session: Session,
    customers: list[Customer],
    techs: list[Technician],
) -> list[CallTranscript]:
    now = datetime.now(timezone.utc)
    scenarios = [
        {
            "call_id": "call_seed_001",
            "customer": customers[1],
            "outcome": "DISPATCHED",
            "intent": "COMPLAINT",
            "sentiment": Decimal("-0.740"),
            "start_risk": Decimal("0.880"),
            "end_risk": Decimal("0.590"),
            "intervention": True,
            "raw": "This is the third time my AC stopped working. I need someone today.",
        },
        {
            "call_id": "call_seed_002",
            "customer": customers[0],
            "outcome": "RETAINED",
            "intent": "SCHEDULING",
            "sentiment": Decimal("-0.210"),
            "start_risk": Decimal("0.720"),
            "end_risk": Decimal("0.480"),
            "intervention": True,
            "raw": "I'd like to schedule maintenance before summer, but I'm worried about pricing.",
        },
        {
            "call_id": "call_seed_003",
            "customer": customers[4],
            "outcome": "ESCALATED_HUMAN",
            "intent": "COMPLAINT",
            "sentiment": Decimal("-0.810"),
            "start_risk": Decimal("0.790"),
            "end_risk": Decimal("0.760"),
            "intervention": False,
            "raw": "Nobody showed up for my appointment window and I want a manager callback.",
        },
        {
            "call_id": "call_seed_004",
            "customer": customers[3],
            "outcome": "FAQ_RESOLVED",
            "intent": "FAQ",
            "sentiment": Decimal("0.420"),
            "start_risk": Decimal("0.180"),
            "end_risk": Decimal("0.160"),
            "intervention": False,
            "raw": "What filter size does my Carrier unit need?",
        },
        {
            "call_id": "call_seed_005",
            "customer": customers[9],
            "outcome": "DISPATCHED",
            "intent": "EMERGENCY",
            "sentiment": Decimal("-0.520"),
            "start_risk": Decimal("0.690"),
            "end_risk": Decimal("0.510"),
            "intervention": True,
            "raw": "Furnace is blowing cold air and we have kids at home.",
        },
    ]
    transcripts: list[CallTranscript] = []
    for idx, scenario in enumerate(scenarios):
        start = now - timedelta(days=idx + 1, hours=2)
        end = start + timedelta(minutes=8 + idx)
        transcripts.append(
            CallTranscript(
                call_id=scenario["call_id"],
                customer_id=scenario["customer"].customer_id,
                technician_id=techs[idx % 2].technician_id,
                call_direction="INBOUND",
                call_start_utc=start,
                call_end_utc=end,
                duration_seconds=int((end - start).total_seconds()),
                call_outcome=scenario["outcome"],
                transcript_raw=scenario["raw"],
                transcript_json=[
                    {
                        "speaker": "customer",
                        "text": scenario["raw"],
                        "start_ms": 0,
                        "end_ms": 45000,
                        "confidence": 0.94,
                    }
                ],
                sentiment_overall=scenario["sentiment"],
                sentiment_trajectory=[{"minute": 0, "score": float(scenario["sentiment"])}],
                dominant_intent=scenario["intent"],
                intent_confidence=Decimal("0.910"),
                entities_extracted={
                    "equipment_mentioned": ["AC_UNIT"],
                    "issue_tags": ["no_cooling", "recurrence"] if idx == 0 else ["scheduling"],
                    "urgency_words": ["today", "emergency"] if idx in {0, 4} else [],
                },
                escalation_detected=scenario["outcome"] == "ESCALATED_HUMAN",
                hesitation_markers={"pause_count": 3, "avg_pause_ms": 420, "filler_word_count": 2},
                emotion_labels={
                    "anger": 0.62 if float(scenario["sentiment"]) < -0.5 else 0.12,
                    "frustration": 0.71 if float(scenario["sentiment"]) < -0.3 else 0.20,
                    "satisfaction": 0.08,
                    "neutral": 0.19,
                },
                churn_risk_at_call_start=scenario["start_risk"],
                churn_risk_at_call_end=scenario["end_risk"],
                intervention_successful=scenario["intervention"],
                rag_queries_issued=1 if scenario["intent"] == "FAQ" else 0,
                tool_calls_log=[
                    {
                        "tool_name": "query_churn_score",
                        "args": {"customer_id": str(scenario["customer"].customer_id)},
                        "result": '{"risk_tier": "HIGH"}',
                        "latency_ms": 42,
                        "timestamp": start.isoformat(),
                    }
                ],
                vapi_metadata={"assistant_id": "seed-assistant", "channel": "pstn"},
            )
        )
    session.add_all(transcripts)
    session.flush()
    return transcripts


EQUIPMENT_PROFILES = [
    ("Carrier", "Infinity 24ANB6", "AC_UNIT", 3),
    ("Trane", "XR16", "AC_UNIT", 7),
    ("Lennox", "EL16XC1", "AC_UNIT", 5),
    ("Carrier", "58MCA", "FURNACE", 9),
    ("Trane", "S9V2", "FURNACE", 11),
    ("Lennox", "ML193", "FURNACE", 6),
    ("Carrier", "25HCC5", "HEAT_PUMP", 4),
    ("Trane", "XV20i", "AC_UNIT", 12),
    ("Lennox", "XC21", "AC_UNIT", 2),
    ("Carrier", "59MN7", "FURNACE", 8),
]


def seed_equipment(session: Session, customers: list[Customer]) -> int:
    """One equipment row per customer (skips customers that already have equipment)."""
    existing_ids = {
        row[0]
        for row in session.query(Equipment.customer_id).distinct().all()
    }
    today = date.today()
    added = 0
    for idx, customer in enumerate(customers):
        if customer.customer_id in existing_ids:
            continue
        make, model, eq_type, age_years = EQUIPMENT_PROFILES[idx % len(EQUIPMENT_PROFILES)]
        install_date = today - timedelta(days=365 * age_years)
        session.add(
            Equipment(
                customer_id=customer.customer_id,
                make=make,
                model=model,
                serial_number=f"SEED-{1000 + idx}-{uuid.uuid4().hex[:6].upper()}",
                equipment_type=eq_type,
                install_date=install_date,
                last_service_date=today - timedelta(days=90 + (idx * 15) % 180),
                service_count=2 + (idx % 5),
                age_years=Decimal(str(age_years)),
                known_issues=["no_cooling"] if idx % 4 == 0 else [],
            )
        )
        added += 1
    session.flush()
    return added


def _churn_probability_for_tier(tier: str, idx: int) -> Decimal:
    if tier == "CRITICAL":
        values = [Decimal("0.880"), Decimal("0.910"), Decimal("0.850"), Decimal("0.930")]
    elif tier == "HIGH":
        values = [Decimal("0.710"), Decimal("0.680"), Decimal("0.750"), Decimal("0.790")]
    elif tier == "MEDIUM":
        values = [Decimal("0.480"), Decimal("0.520")]
    else:
        values = [Decimal("0.220"), Decimal("0.180")]
    return values[idx % len(values)]


def seed_churn_scores(session: Session, customers: list[Customer]) -> int:
    """Insert churn_scores for HIGH/CRITICAL customers missing a score row."""
    added = 0
    for idx, customer in enumerate(customers):
        tier = str((customer.metadata_ or {}).get("churn_tier", "LOW")).upper()
        if tier not in {"HIGH", "CRITICAL"}:
            continue
        existing = (
            session.query(ChurnScore)
            .filter(
                ChurnScore.entity_type == "CUSTOMER",
                ChurnScore.entity_id == customer.customer_id,
            )
            .first()
        )
        if existing is not None:
            continue
        prob = _churn_probability_for_tier(tier, idx)
        session.add(
            ChurnScore(
                entity_type="CUSTOMER",
                entity_id=customer.customer_id,
                churn_probability=prob,
                risk_tier=tier,
                feature_contributions=[
                    {
                        "feature": "escalation_frequency",
                        "shap_value": 0.12,
                        "direction": "INCREASES_RISK",
                    }
                ],
                model_version="seed_v1",
                scoring_trigger="SEED_SCRIPT",
                prediction_horizon_days=90,
            )
        )
        added += 1
    session.flush()
    return added


def main() -> None:
    engine = create_engine(sync_database_url())
    with Session(engine) as session:
        existing = session.query(Customer).count()
        if existing > 0:
            customers = session.query(Customer).order_by(Customer.full_name).all()
            equipment_added = seed_equipment(session, customers)
            churn_added = seed_churn_scores(session, customers)
            session.commit()
            print(
                f"Backfill on existing DB ({existing} customers): "
                f"+{equipment_added} equipment, +{churn_added} churn_scores."
            )
            return

        techs = seed_technicians(session)
        customers = seed_customers(session, techs)
        equipment_added = seed_equipment(session, customers)
        churn_added = seed_churn_scores(session, customers)
        transcripts = seed_call_transcripts(session, customers, techs)
        session.commit()
        print(
            f"Seeded {len(techs)} technicians, {len(customers)} customers, "
            f"{equipment_added} equipment, {churn_added} churn_scores, "
            f"{len(transcripts)} call transcripts."
        )


if __name__ == "__main__":
    main()
