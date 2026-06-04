from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_system_health_returns_200(api_client):
    response = await api_client.get("/api/v1/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("healthy", "degraded", "unhealthy")
    assert "components" in body
    assert "database" in body["components"]
    assert "metrics" in body
    assert "total_organizations" in body["metrics"]


@pytest.mark.asyncio
async def test_system_health_healthy_when_db_ok(api_client):
    response = await api_client.get("/api/v1/system/health")
    body = response.json()
    assert body["components"]["database"]["status"] == "ok"
    if body["status"] != "unhealthy":
        assert body["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_system_health_degraded_when_redis_slow(api_client):
    from app.services.system_health_service import SystemHealthService

    with patch.object(
        SystemHealthService,
        "_check_redis",
        new_callable=AsyncMock,
        return_value={"status": "degraded", "error": "timeout", "latency_ms": 2000},
    ):
        response = await api_client.get("/api/v1/system/health")
    body = response.json()
    assert body["components"]["redis"]["status"] == "degraded"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_system_health_metrics_counts(api_client, seeded_customer):
    del seeded_customer
    response = await api_client.get("/api/v1/system/health")
    metrics = response.json()["metrics"]
    assert metrics["total_customers"] >= 1
    assert metrics["total_organizations"] >= 1
