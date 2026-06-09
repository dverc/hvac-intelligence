"""
Pytest fixtures — async PostgreSQL (asyncpg), httpx AsyncClient, and service mocks.

Requires a migrated test database (default: hvac_intel_test). Set TEST_DATABASE_URL to override.
Falls back to DATABASE_URL with db name hvac_intel_test when unset.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Environment (before app imports) ───────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _candidate_database_urls() -> list[str]:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return [explicit]
    base = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://hvac_user:changeme@localhost:5432/hvac_intel",
    )
    candidates = []
    if "hvac_intel_test" not in base:
        if "/hvac_intel" in base:
            candidates.append(base.replace("/hvac_intel", "/hvac_intel_test"))
        else:
            candidates.append(base.rsplit("/", 1)[0] + "/hvac_intel_test")
    candidates.append(base)
    return candidates


TEST_DATABASE_URLS = _candidate_database_urls()
os.environ["DATABASE_URL"] = TEST_DATABASE_URLS[0]

_DEFAULTS = {
    "ANTHROPIC_API_KEY": "test-anthropic",
    "OPENAI_API_KEY": "sk-test-openai",
    "VAPI_API_KEY": "test-vapi",
    "VAPI_WEBHOOK_SECRET": "test-webhook-secret",
    "VAPI_ASSISTANT_ID": "test-assistant",
    "PINECONE_API_KEY": "pc-dev-test",
    "PINECONE_ENVIRONMENT": "us-east-1",
    "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
    "REDIS_URL": "redis://localhost:6379/15",
    "MODEL_ARTIFACTS_PATH": "./ml/artifacts",
    "RAG_MOCK_INDEX_PATH": "data/knowledge/.mock_vector_index.json",
    "DASHBOARD_API_KEY": "test-api-key-for-tests",
    "JWT_SECRET_KEY": "test-jwt-secret-for-tests",
    "ENVIRONMENT": "development",
    "VAPI_WEBHOOK_HMAC_BYPASS": "false",
    "GOOGLE_CLIENT_ID": "test-google-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-google-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/api/v1/integrations/google/oauth/callback",
    "GOOGLE_TOKEN_ENCRYPTION_KEY": "",
    "FRONTEND_BASE_URL": "http://localhost:3000",
    "JOBBER_CLIENT_ID": "test-jobber-client-id",
    "JOBBER_CLIENT_SECRET": "test-jobber-secret",
    "JOBBER_OAUTH_REDIRECT_URI": "http://localhost:8000/api/v1/integrations/jobber/oauth/callback",
}
for _key, _value in _DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_engine, get_session_factory  # noqa: E402
import app.models  # noqa: E402,F401  (register all ORM tables on Base.metadata)

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def relax_test_rate_limits():
    """
    Raise SlowAPI global application limit during tests so the shared
    127.0.0.1 key from ASGITransport does not trip 60/minute mid-suite.
    Production limiter config in app/core/rate_limit.py is unchanged.
    """
    from app.core.rate_limit import limiter

    original_providers: list[str | object] = []
    for group in limiter._application_limits:
        original_providers.append(group._LimitGroup__limit_provider)
        group._LimitGroup__limit_provider = "10000/minute"
    yield
    for group, original in zip(limiter._application_limits, original_providers):
        group._LimitGroup__limit_provider = original


def sign_vapi_payload(payload: dict[str, Any], secret: str | None = None) -> tuple[bytes, str]:
    """HMAC-SHA256 signature matching production verify_vapi_signature."""
    secret = secret or get_settings().VAPI_WEBHOOK_SECRET
    body = json.dumps(payload).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, f"sha256={digest}"


@pytest.fixture
def sample_transcript() -> list[dict]:
    data = json.loads((FIXTURES_DIR / "sample_vapi_transcript.json").read_text())
    messages = data.get("messages", [])
    return [
        {
            "speaker": "customer" if m.get("role") == "user" else "agent",
            "text": m.get("message", ""),
            "words": m.get("words", []),
        }
        for m in messages
        if m.get("role") == "user"
    ]


@pytest.fixture
def sample_feature_vector() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "sample_feature_vector.json").read_text())


class MockChurnModelEnsemble:
    """Fixed prediction without loading pickle artifacts."""

    FEATURE_ORDER = __import__(
        "app.ml.churn_schema", fromlist=["FEATURE_ORDER"]
    ).FEATURE_ORDER

    def __init__(self) -> None:
        self._ready = True
        self.model_version = "mock_v1"

    @property
    def is_ready(self) -> bool:
        return self._ready

    def predict(self, feature_dict: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "ok",
            "churn_probability": 0.62,
            "risk_tier": "HIGH",
            "feature_contributions": [
                {
                    "feature": "escalation_frequency",
                    "shap_value": 0.12,
                    "direction": "INCREASES_RISK",
                }
            ],
            "model_version": self.model_version,
        }


@pytest.fixture
def mock_churn_ensemble() -> MockChurnModelEnsemble:
    return MockChurnModelEnsemble()


class MockRAGRetriever:
    async def retrieve(
        self,
        query: str,
        namespace: str | None = None,
        top_k: int = 5,
        filter_model: str | None = None,
    ) -> list[dict]:
        return [
            {
                "chunk_id": "chunk-fixture-1",
                "text": f"Fixture answer for: {query}",
                "source": "faq_general.md",
                "similarity_score": 0.91,
                "namespace": namespace or "faq_general",
            }
        ]


@pytest.fixture
def mock_rag_retriever() -> MockRAGRetriever:
    return MockRAGRetriever()


class MockToolExecutor:
    """Stub all six Vapi tools for webhook routing tests."""

    def __init__(self) -> None:
        self.customer_service = MagicMock()
        self.customer_service.get_call_context = AsyncMock(
            return_value={
                "variable_values": {
                    "customer_name": "Test Customer",
                    "equipment_info": "Carrier AC",
                    "churn_risk": "LOW",
                    "retention_protocol": "",
                    "company_name": "HVAC Intelligence Demo",
                },
                "system_prompt_injection": "Test system prompt",
                "first_message": None,
            }
        )
        self.customer_service.lookup_by_phone = AsyncMock(return_value=None)
        self.churn_service = MagicMock()
        self.churn_service.get_latest_score = AsyncMock(
            return_value={
                "risk_tier": "LOW",
                "churn_probability": 0.2,
            }
        )
        self.calls: list[tuple[str, dict]] = []
        # Tenant context attributes mirrored from the real ToolExecutor.
        self.org_id = None
        self.org_settings = None
        self.db = None

    def set_tenant(self, org_id, settings=None, org_slug=None) -> None:
        self.org_id = org_id
        self.org_settings = settings
        self.org_slug = org_slug

    async def execute_batch(self, tool_call_list: list[dict]) -> list[dict]:
        from app.services.tool_executor import _parse_vapi_tool_call

        results = []
        for tool_call in tool_call_list:
            tool_id, name, _ = _parse_vapi_tool_call(tool_call)
            self.calls.append((name, tool_call))
            payloads = {
                "schedule_dispatch": {"job_number": "DX-TEST-1", "job_id": str(uuid.uuid4())},
                "query_churn_score": {
                    "churn_probability": 0.71,
                    "risk_tier": "HIGH",
                    "customer_id": "cust-1",
                },
                "get_customer_info": {"found": True, "full_name": "Test Customer"},
                "get_equipment_info": {"found": True, "equipment": []},
                "rag_knowledge_query": {"retrieved_context": [{"chunk_id": "c1"}]},
                "create_support_ticket": {"success": True, "ticket": {"ticket_id": "t1"}},
            }
            results.append(
                {
                    "toolCallId": tool_id,
                    "result": json.dumps(payloads.get(name, {"ok": True})),
                }
            )
        return results


@pytest.fixture
def mock_tool_executor() -> MockToolExecutor:
    return MockToolExecutor()


@pytest_asyncio.fixture(scope="session")
async def database_ready() -> AsyncGenerator[Any, None]:
    """Ensure schema + views exist on the async test database."""
    engine = None
    last_error: Exception | None = None

    for url in TEST_DATABASE_URLS:
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()

        candidate = get_engine()
        try:
            async with candidate.connect() as conn:
                await conn.execute(text("SELECT 1"))
            engine = candidate
            break
        except Exception as exc:
            last_error = exc
            await candidate.dispose()

    if engine is None:
        pytest.skip(f"Async test database unavailable: {last_error}")

    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
    )
    get_engine.cache_clear()

    # SAFETY: only ever reset a database whose name marks it as a test DB.
    # This prevents the destructive DROP SCHEMA from running against the dev DB
    # if the test DB URL ever falls back to the primary database.
    active_db_url = os.environ["DATABASE_URL"]
    is_test_db = "test" in active_db_url.rsplit("/", 1)[-1].lower()

    async with engine.begin() as conn:
        if is_test_db:
            # Reset the test schema so model changes (e.g. new org_id columns)
            # always apply cleanly regardless of prior runs' DDL.
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Seed organization (matches migration 005) so FK org_id and the column
        # server_default resolve in the test database.
        from app.core.constants import SEED_ORG_ID_STR

        await conn.execute(
            text(
                """
                INSERT INTO organizations
                    (org_id, org_name, slug, industry, business_phone,
                     plan_tier, is_active, settings)
                VALUES
                    (CAST(:org_id AS UUID), 'HVAC Intelligence Demo', 'hvac-demo',
                     'hvac', '+19498800687', 'professional', true,
                     CAST(:settings AS JSONB))
                ON CONFLICT (org_id) DO NOTHING
                """
            ).bindparams(
                org_id=SEED_ORG_ID_STR,
                settings='{"pinecone_namespace": "faq_general"}',
            )
        )
        await conn.execute(
            text(
                """
                CREATE OR REPLACE VIEW v_equipment_computed AS
                SELECT
                    e.*,
                    CASE
                        WHEN e.install_date IS NOT NULL THEN
                            EXTRACT(YEAR FROM AGE(NOW(), e.install_date))::NUMERIC(5, 2)
                        ELSE NULL
                    END AS age_years_computed
                FROM equipment e;
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE OR REPLACE VIEW v_technicians_computed AS
                SELECT
                    t.*,
                    EXTRACT(YEAR FROM AGE(NOW(), t.hire_date))::NUMERIC(5, 2) AS tenure_years_computed
                FROM technicians t;
                """
            )
        )

    yield engine

    await engine.dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session(database_ready) -> AsyncGenerator[AsyncSession, None]:
    """Async session with rollback after each test (asyncpg)."""
    engine = database_ready
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def seeded_customer(db_session: AsyncSession) -> dict[str, Any]:
    """Seed one HIGH-risk customer with equipment, call, job, and ticket."""
    from app.core.constants import SEED_ORG_ID
    from app.models.call_transcript import CallTranscript
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob
    from app.models.equipment import Equipment
    from app.models.support_ticket import SupportTicket
    from app.models.technician import Technician
    from app.models.technician_schedule import TechnicianSchedule

    tech = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-TEST-{uuid.uuid4().hex[:8]}",
        full_name="Test Tech",
        phone="+15550001111",
        hire_date=date(2020, 1, 1),
        tenure_years=Decimal("5"),
    )
    db_session.add(tech)
    await db_session.flush()

    for dow in range(5):
        db_session.add(
            TechnicianSchedule(
                org_id=SEED_ORG_ID,
                technician_id=tech.technician_id,
                day_of_week=dow,
                start_time=datetime.strptime("08:00", "%H:%M").time(),
                end_time=datetime.strptime("17:00", "%H:%M").time(),
                is_active=True,
                effective_from=date.today(),
            )
        )
    await db_session.flush()

    phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    customer = Customer(
        org_id=SEED_ORG_ID,
        full_name="Sarah Mitchell",
        phone_primary=phone,
        customer_since=date(2019, 6, 1),
        contract_type="ANNUAL_MAINTENANCE",
        contract_value_usd=Decimal("2400.00"),
        metadata_={
            "churn_tier": "HIGH",
            "churn_probability": 0.71,
            "payment_delay_days_avg": 12,
            "payment_failure_count": 2,
        },
    )
    db_session.add(customer)
    await db_session.flush()

    equipment = Equipment(
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        make="Carrier",
        model="Infinity 24",
        equipment_type="AC_UNIT",
        install_date=date(2018, 5, 1),
        last_service_date=date(2025, 1, 15),
    )
    db_session.add(equipment)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    transcript = CallTranscript(
        call_id="call-seed-001",
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        call_direction="INBOUND",
        call_start_utc=now - timedelta(days=2),
        call_end_utc=now - timedelta(days=2) + timedelta(minutes=8),
        duration_seconds=480,
        call_outcome="DISPATCHED",
        sentiment_overall=Decimal("-0.55"),
        sentiment_trajectory=[{"minute": 0, "score": -0.2}, {"minute": 1, "score": -0.7}],
        escalation_detected=True,
        churn_risk_at_call_start=Decimal("0.78"),
        churn_risk_at_call_end=Decimal("0.61"),
        intervention_successful=True,
        hesitation_markers={"pause_count": 2, "filler_word_count": 3},
        emotion_labels={"anger": 0.4, "frustration": 0.35},
    )
    db_session.add(transcript)
    await db_session.flush()

    job = DispatchJob(
        job_number="DX-SEED-001",
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        equipment_id=equipment.equipment_id,
        technician_id=tech.technician_id,
        call_transcript_id=transcript.transcript_id,
        issue_type="AC_FAILURE",
        priority="P1",
        job_status="SCHEDULED",
        created_at=now - timedelta(days=2),
        actual_completion=now - timedelta(days=1),
        customer_rating=4,
    )
    db_session.add(job)

    ticket = SupportTicket(
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        call_transcript_id=transcript.transcript_id,
        ticket_type="COMPLAINT_ESCALATION",
        subject="Repeat AC failure",
        description="Third recurrence this summer",
        priority="P2",
        status="OPEN",
    )
    db_session.add(ticket)
    await db_session.flush()

    return {
        "customer": customer,
        "customer_id": str(customer.customer_id),
        "equipment_id": str(equipment.equipment_id),
        "technician_id": str(tech.technician_id),
        "transcript_id": str(transcript.transcript_id),
        "phone": customer.phone_primary,
    }


@pytest_asyncio.fixture
async def make_org(db_session: AsyncSession):
    """Factory: create an active Organization with unique slug/phone."""
    from app.models.organization import Organization

    async def _make(
        *,
        name: str,
        slug: str | None = None,
        business_phone: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Organization:
        org = Organization(
            org_name=name,
            slug=slug or f"org-{uuid.uuid4().hex[:8]}",
            industry="hvac",
            business_phone=business_phone,
            plan_tier="starter",
            is_active=True,
            settings=settings or {},
        )
        db_session.add(org)
        await db_session.flush()
        return org

    return _make


@pytest_asyncio.fixture
async def make_customer(db_session: AsyncSession):
    """Factory: create a Customer under a given org_id."""
    from app.models.customer import Customer

    async def _make(*, org_id, full_name: str = "Test Customer") -> Customer:
        phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
        customer = Customer(
            org_id=org_id,
            full_name=full_name,
            phone_primary=phone,
            customer_since=date(2020, 1, 1),
            contract_type="RESIDENTIAL_OTC",
            metadata_={"churn_tier": "LOW"},
        )
        db_session.add(customer)
        await db_session.flush()
        return customer

    return _make


@pytest.fixture
def sync_db_session(database_ready):
    """Sync session for FeatureBuilder (uses psycopg2 / asyncpg-compatible URL)."""
    from app.ml.sync_db import get_sync_engine

    get_sync_engine.cache_clear()
    from sqlalchemy.orm import Session

    engine = get_sync_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def seeded_sync_customer(sync_db_session):
    """Seeded customer visible to sync FeatureBuilder (committed within connection)."""
    from app.models.call_transcript import CallTranscript
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob
    from app.models.equipment import Equipment
    from app.models.support_ticket import SupportTicket
    from app.models.technician import Technician

    tech = Technician(
        employee_number=f"T-SYNC-{uuid.uuid4().hex[:8]}",
        full_name="Sync Tech",
        phone="+15550002222",
        hire_date=date(2020, 1, 1),
        tenure_years=Decimal("5"),
    )
    sync_db_session.add(tech)
    sync_db_session.flush()

    sync_phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    customer = Customer(
        full_name="Sync Test Customer",
        phone_primary=sync_phone,
        customer_since=date(2019, 1, 1),
        contract_type="ANNUAL_MAINTENANCE",
        contract_value_usd=Decimal("1800.00"),
        metadata_={
            "churn_tier": "HIGH",
            "payment_failure_count": 2,
            "payment_delay_days_avg": 10,
        },
    )
    sync_db_session.add(customer)
    sync_db_session.flush()

    equipment = Equipment(
        customer_id=customer.customer_id,
        make="Trane",
        model="XR16",
        install_date=date(2017, 3, 1),
        last_service_date=date(2025, 2, 1),
    )
    sync_db_session.add(equipment)
    sync_db_session.flush()

    now = datetime.now(timezone.utc)
    transcript = CallTranscript(
        call_id="call-sync-001",
        customer_id=customer.customer_id,
        call_direction="INBOUND",
        call_start_utc=now - timedelta(days=5),
        call_end_utc=now - timedelta(days=5) + timedelta(minutes=10),
        duration_seconds=600,
        call_outcome="ESCALATED_HUMAN",
        sentiment_overall=Decimal("-0.6"),
        sentiment_trajectory=[{"minute": 0, "score": -0.3}, {"minute": 1, "score": -0.8}],
        escalation_detected=True,
        churn_risk_at_call_start=Decimal("0.75"),
        churn_risk_at_call_end=Decimal("0.55"),
        intervention_successful=True,
        hesitation_markers={"pause_count": 3, "filler_word_count": 4},
        emotion_labels={"anger": 0.5, "frustration": 0.3},
        vapi_metadata={"recurrence_complaint_detected": True},
    )
    sync_db_session.add(transcript)
    sync_db_session.flush()

    job = DispatchJob(
        job_number="DX-SYNC-001",
        customer_id=customer.customer_id,
        equipment_id=equipment.equipment_id,
        technician_id=tech.technician_id,
        call_transcript_id=transcript.transcript_id,
        issue_type="AC_FAILURE",
        priority="P1",
        job_status="COMPLETED",
        created_at=now - timedelta(days=4),
        actual_completion=now - timedelta(days=3),
        customer_rating=3,
    )
    sync_db_session.add(job)

    ticket = SupportTicket(
        customer_id=customer.customer_id,
        ticket_type="COMPLAINT_ESCALATION",
        subject="Sync ticket",
        description="Noise recurrence",
        priority="P1",
        status="OPEN",
    )
    sync_db_session.add(ticket)
    sync_db_session.flush()

    return {
        "customer_id": str(customer.customer_id),
        "customer": customer,
    }


@pytest.fixture
def dashboard_api_key() -> str:
    """Signing key for dashboard API and OAuth state (matches service settings)."""
    return get_settings().DASHBOARD_API_KEY


async def _create_admin_user(db_session: AsyncSession) -> tuple[str, str]:
    """Insert an admin user and return (email, password)."""
    from passlib.context import CryptContext

    from app.core.constants import SEED_ORG_ID_STR
    from app.models.user import User

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    email = f"admin-{uuid.uuid4().hex[:8]}@test.local"
    password = "TestAdminPass123!"
    user = User(
        org_id=SEED_ORG_ID_STR,
        email=email,
        hashed_password=pwd_context.hash(password),
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return email, password


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    mock_tool_executor: MockToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient with X-API-Key (for register and unauthenticated auth tests)."""
    from app.api import deps
    from app.main import app
    from app.pipeline import event_bus

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_build_tool_executor(_db):
        return mock_tool_executor

    monkeypatch.setattr(event_bus, "publish_call_active_event", AsyncMock())

    app.dependency_overrides[deps.get_db] = override_get_db
    monkeypatch.setattr(deps, "build_tool_executor", override_build_tool_executor)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": get_settings().DASHBOARD_API_KEY},
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client: JWT Bearer + X-API-Key for protected dashboard routes."""
    from app.core.rate_limit import limiter

    settings = get_settings()
    email, password = await _create_admin_user(db_session)

    transport = api_client._transport
    limiter.enabled = False
    try:
        login_resp = await api_client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
    finally:
        limiter.enabled = True
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-API-Key": settings.DASHBOARD_API_KEY,
            "Authorization": f"Bearer {token}",
        },
    ) as client:
        yield client
