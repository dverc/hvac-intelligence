from __future__ import annotations

import asyncio
import json
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.auth import verify_api_key
from app.core.auth_jwt import get_current_user, verify_access_token
from app.core.cache import get_redis_client
from app.pipeline.event_bus import ALL_SSE_CHANNELS, EventBus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])

SSE_PING_INTERVAL_SECONDS = 15.0
SSE_TOKEN_TTL_SECONDS = 60
SSE_TOKEN_KEY_PREFIX = "sse_token:"


def _sse_token_key(token: str) -> str:
    return f"{SSE_TOKEN_KEY_PREFIX}{token}"


async def _consume_sse_token(token: str) -> str | None:
    """Validate a one-time SSE token and return the bound org_id."""
    redis = get_redis_client()
    org_id = await redis.getdel(_sse_token_key(token))
    if org_id is None:
        return None
    return str(org_id)


async def _resolve_stream_org_id(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        payload = verify_access_token(token)
        if payload:
            org_id = payload.get("org_id")
            return str(org_id) if org_id else None

    query_token = request.query_params.get("token")
    if query_token:
        return await _consume_sse_token(query_token)

    return None


def _event_belongs_to_org(event: dict, stream_org_id: str) -> bool:
    if event.get("event_type") == "STREAM_ERROR":
        return True
    event_org_id = event.get("org_id")
    if event_org_id is None:
        return False
    return str(event_org_id) == stream_org_id


@router.post("/sse-token")
async def create_sse_token(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(verify_api_key),
) -> dict[str, str]:
    """Issue a short-lived one-time token for EventSource (cannot send auth headers)."""
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    token = secrets.token_urlsafe(32)
    redis = get_redis_client()
    await redis.set(_sse_token_key(token), str(org_id), ex=SSE_TOKEN_TTL_SECONDS)
    return {"token": token}


@router.get("/churn-events")
async def stream_churn_events(request: Request) -> StreamingResponse:
    """
    Server-Sent Events endpoint for the real-time dashboard feed.
    Subscribes to Redis pub/sub channels: call.active, churn.intervention, batch.complete.
    Emits comment keepalives every 15s so idle connections survive ≥60s.
    """
    stream_org_id = await _resolve_stream_org_id(request)
    if stream_org_id is None:
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

                if not _event_belongs_to_org(event, stream_org_id):
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
