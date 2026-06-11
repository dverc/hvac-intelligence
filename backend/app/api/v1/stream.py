from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.auth_jwt import verify_access_token
from app.core.config import get_settings
from app.pipeline.event_bus import ALL_SSE_CHANNELS, EventBus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])

SSE_PING_INTERVAL_SECONDS = 15.0


def _stream_authorized(request: Request) -> bool:
    settings = get_settings()
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if verify_access_token(token):
            return True

    query_token = request.query_params.get("token")
    if query_token and verify_access_token(query_token):
        return True

    api_key = request.query_params.get("api_key") or request.headers.get("X-API-Key")
    return bool(api_key and api_key == settings.DASHBOARD_API_KEY)


@router.get("/churn-events")
async def stream_churn_events(request: Request) -> StreamingResponse:
    """
    Server-Sent Events endpoint for the real-time dashboard feed.
    Subscribes to Redis pub/sub channels: call.active, churn.intervention, batch.complete.
    Emits comment keepalives every 15s so idle connections survive ≥60s.
    """
    if not _stream_authorized(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    async def event_generator():
        listener_task: asyncio.Task | None = None
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def redis_listener() -> None:
            try:
                async with EventBus() as bus:
                    async for event in bus.subscribe(list(ALL_SSE_CHANNELS)):
                        await queue.put(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("SSE Redis listener error: %s", exc)
                await queue.put(None)

        listener_task = asyncio.create_task(redis_listener())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=SSE_PING_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if event is None:
                    yield f"data: {json.dumps({'event_type': 'STREAM_ERROR', 'message': 'redis disconnected'})}\n\n"
                    await asyncio.sleep(SSE_PING_INTERVAL_SECONDS)
                    continue

                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)
        finally:
            if listener_task is not None:
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
