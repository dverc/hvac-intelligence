from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

OK_CHECK = {"status": "ok", "latency_ms": 5, "detail": ""}


@pytest.mark.asyncio
async def test_deep_health_returns_healthy_when_all_checks_pass(auth_client):
    with (
        patch("app.api.v1.system._check_database", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_redis", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_pinecone", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_celery", AsyncMock(return_value=OK_CHECK)),
    ):
        response = await auth_client.get("/api/v1/system/health/deep")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"
    assert "timestamp" in body
    assert set(body["checks"]) == {"database", "redis", "pinecone", "celery"}
    for check in body["checks"].values():
        assert isinstance(check["latency_ms"], (int, float))


@pytest.mark.asyncio
async def test_deep_health_returns_degraded_when_pinecone_fails(auth_client):
    pinecone_error = {
        "status": "error",
        "latency_ms": 45,
        "detail": "connection refused",
    }
    with (
        patch("app.api.v1.system._check_database", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_redis", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_pinecone", AsyncMock(return_value=pinecone_error)),
        patch("app.api.v1.system._check_celery", AsyncMock(return_value=OK_CHECK)),
    ):
        response = await auth_client.get("/api/v1/system/health/deep")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["pinecone"]["status"] == "error"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_deep_health_returns_unhealthy_when_database_fails(auth_client):
    db_error = {
        "status": "error",
        "latency_ms": 12,
        "detail": "connection refused",
    }
    with (
        patch("app.api.v1.system._check_database", AsyncMock(return_value=db_error)),
        patch("app.api.v1.system._check_redis", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_pinecone", AsyncMock(return_value=OK_CHECK)),
        patch("app.api.v1.system._check_celery", AsyncMock(return_value=OK_CHECK)),
    ):
        response = await auth_client.get("/api/v1/system/health/deep")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"]["status"] == "error"


@pytest.mark.asyncio
async def test_deep_health_check_results_include_latency_ms(auth_client):
    checks = {
        "database": {"status": "ok", "latency_ms": 12, "detail": ""},
        "redis": {"status": "ok", "latency_ms": 3, "detail": ""},
        "pinecone": {"status": "ok", "latency_ms": 45, "detail": "not configured"},
        "celery": {"status": "ok", "latency_ms": 8, "detail": ""},
    }
    with (
        patch("app.api.v1.system._check_database", AsyncMock(return_value=checks["database"])),
        patch("app.api.v1.system._check_redis", AsyncMock(return_value=checks["redis"])),
        patch("app.api.v1.system._check_pinecone", AsyncMock(return_value=checks["pinecone"])),
        patch("app.api.v1.system._check_celery", AsyncMock(return_value=checks["celery"])),
    ):
        response = await auth_client.get("/api/v1/system/health/deep")

    body = response.json()
    for name, expected in checks.items():
        assert body["checks"][name]["latency_ms"] == expected["latency_ms"]
        assert isinstance(body["checks"][name]["latency_ms"], (int, float))
