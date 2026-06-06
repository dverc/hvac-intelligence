from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.pipeline.celery_app import celery_app

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db)) -> dict:
    from app.services.system_health_service import SystemHealthService

    service = SystemHealthService(db)
    return await service.get_health()


def _compute_overall_status(checks: dict[str, dict[str, Any]]) -> str:
    db_ok = checks["database"]["status"] == "ok"
    redis_ok = checks["redis"]["status"] == "ok"
    if not db_ok or not redis_ok:
        return "unhealthy"
    if checks["pinecone"]["status"] != "ok" or checks["celery"]["status"] != "ok":
        return "degraded"
    return "healthy"


async def _check_database(db: AsyncSession) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "ok", "latency_ms": latency_ms, "detail": ""}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "error", "latency_ms": latency_ms, "detail": str(exc)}


async def _check_redis() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        import redis.asyncio as redis

        settings = get_settings()
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        try:
            await client.ping()
        finally:
            await client.aclose()
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "ok", "latency_ms": latency_ms, "detail": ""}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "error", "latency_ms": latency_ms, "detail": str(exc)}


async def _check_pinecone() -> dict[str, Any]:
    start = time.perf_counter()
    settings = get_settings()
    pinecone_key = (settings.PINECONE_API_KEY or "").strip()
    if not pinecone_key or pinecone_key.startswith("pc-dev"):
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "ok", "latency_ms": latency_ms, "detail": "not configured"}

    try:
        def _describe_index() -> None:
            from app.api.deps import get_rag_retriever

            retriever = get_rag_retriever()
            if retriever._pinecone_index is None:
                raise RuntimeError("Pinecone index not initialized")
            retriever._pinecone_index.describe_index_stats()

        await asyncio.to_thread(_describe_index)
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "ok", "latency_ms": latency_ms, "detail": ""}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "error", "latency_ms": latency_ms, "detail": str(exc)}


def _check_celery_sync() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        inspect = celery_app.control.inspect(timeout=2)
        ping_result = inspect.ping()
        latency_ms = round((time.perf_counter() - start) * 1000)
        if not ping_result:
            return {
                "status": "error",
                "latency_ms": latency_ms,
                "detail": "no workers responding",
            }
        return {"status": "ok", "latency_ms": latency_ms, "detail": ""}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"status": "error", "latency_ms": latency_ms, "detail": str(exc)}


async def _check_celery() -> dict[str, Any]:
    return await asyncio.to_thread(_check_celery_sync)


@router.get("/health/deep")
async def deep_health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    database, redis, pinecone, celery = await asyncio.gather(
        _check_database(db),
        _check_redis(),
        _check_pinecone(),
        _check_celery(),
    )
    checks = {
        "database": database,
        "redis": redis,
        "pinecone": pinecone,
        "celery": celery,
    }
    overall = _compute_overall_status(checks)
    settings = get_settings()
    body = {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "checks": checks,
    }
    status_code = 503 if overall == "unhealthy" else 200
    return JSONResponse(content=body, status_code=status_code)
