from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import api_router, google_oauth_router, jobber_oauth_router, vapi_router
from app.core.auth import request_has_valid_api_key, verify_api_key
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import limiter

settings = get_settings()
configure_logging(settings.DEBUG)


def _docs_are_public() -> bool:
    return settings.ENVIRONMENT == "development" or settings.DEBUG


async def _rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_openapi_docs(request: Request, call_next: Callable) -> Response:
    if request.url.path in ("/docs", "/redoc", "/openapi.json") and not _docs_are_public():
        if not request_has_valid_api_key(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
    return await call_next(request)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Callable) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    return response


@app.get("/health")
@limiter.exempt
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


app.include_router(vapi_router)
app.include_router(google_oauth_router)
app.include_router(jobber_oauth_router)
app.include_router(api_router, dependencies=[Depends(verify_api_key)])

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
