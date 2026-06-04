from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.call_transcript import CallTranscript
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.organization import Organization
from app.rag.indexer import KnowledgeIndexer


class SystemHealthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def get_health(self) -> dict[str, Any]:
        components: dict[str, Any] = {}
        db_result = await self._check_database()
        components["database"] = db_result

        redis_result = await self._check_redis()
        components["redis"] = redis_result

        pinecone_result = await self._check_pinecone()
        components["pinecone"] = pinecone_result

        vapi_result = await self._check_vapi_webhook()
        components["vapi_webhook"] = vapi_result

        metrics = await self._collect_metrics()

        if db_result.get("status") != "ok":
            overall = "unhealthy"
        elif any(c.get("status") == "degraded" for c in components.values()):
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "metrics": metrics,
        }

    async def _timed(self, coro) -> tuple[dict[str, Any], float]:
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(coro, timeout=2.0)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return result, latency_ms
        except asyncio.TimeoutError:
            return {"status": "degraded", "error": "timeout"}, 2000.0
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {"status": "degraded", "error": str(exc)}, latency_ms

    async def _check_database(self) -> dict[str, Any]:
        async def _run() -> dict[str, Any]:
            await self.db.execute(text("SELECT 1"))
            return {"status": "ok"}

        payload, latency_ms = await self._timed(_run())
        payload["latency_ms"] = latency_ms
        return payload

    async def _check_redis(self) -> dict[str, Any]:
        async def _run() -> dict[str, Any]:
            import redis.asyncio as redis

            client = redis.from_url(self.settings.REDIS_URL, socket_connect_timeout=2)
            try:
                await client.ping()
                return {"status": "ok"}
            finally:
                await client.aclose()

        payload, latency_ms = await self._timed(_run())
        payload["latency_ms"] = latency_ms
        return payload

    async def _check_pinecone(self) -> dict[str, Any]:
        async def _run() -> dict[str, Any]:
            indexer = KnowledgeIndexer()
            counts = indexer.get_namespace_counts()
            vector_count = sum(counts.values())
            return {"status": "ok", "vector_count": vector_count}

        payload, latency_ms = await self._timed(_run())
        payload["latency_ms"] = latency_ms
        return payload

    async def _check_vapi_webhook(self) -> dict[str, Any]:
        async def _run() -> dict[str, Any]:
            last_call = (
                await self.db.execute(
                    select(CallTranscript.call_start_utc)
                    .order_by(CallTranscript.call_start_utc.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            payload: dict[str, Any] = {"status": "ok"}
            if last_call is not None:
                ts = last_call
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                payload["last_call_at"] = ts.isoformat()
            return payload

        payload, latency_ms = await self._timed(_run())
        payload["latency_ms"] = latency_ms
        return payload

    async def _collect_metrics(self) -> dict[str, int]:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        org_count = (
            await self.db.execute(
                select(func.count()).select_from(Organization).where(
                    Organization.is_active.is_(True)
                )
            )
        ).scalar_one() or 0
        customer_count = (
            await self.db.execute(select(func.count()).select_from(Customer))
        ).scalar_one() or 0
        calls_today = (
            await self.db.execute(
                select(func.count())
                .select_from(CallTranscript)
                .where(CallTranscript.call_start_utc >= today_start)
            )
        ).scalar_one() or 0
        open_jobs = (
            await self.db.execute(
                select(func.count())
                .select_from(DispatchJob)
                .where(DispatchJob.job_status.in_(["SCHEDULED", "IN_PROGRESS"]))
            )
        ).scalar_one() or 0
        return {
            "total_organizations": int(org_count),
            "total_customers": int(customer_count),
            "total_calls_today": int(calls_today),
            "total_dispatch_jobs_open": int(open_jobs),
        }
