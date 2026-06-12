"""Prometheus metrics (§6 Phase 7)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import Counter, Gauge, Histogram

vapi_webhook_total = Counter(
    "vapi_webhook_total",
    "Total Vapi webhook events",
    ["event_type"],
)
tool_execution_latency = Histogram(
    "tool_execution_latency_seconds",
    "Tool execution latency",
    ["tool_name"],
)
churn_scoring_latency = Histogram(
    "churn_scoring_latency_seconds",
    "ML model scoring latency",
)
high_risk_accounts_gauge = Gauge(
    "high_risk_accounts_total",
    "Current HIGH+CRITICAL accounts",
)
saved_by_ai_counter = Counter(
    "saved_by_ai_total",
    "AI-attributed retention interventions",
)
rag_retrieval_latency = Histogram(
    "rag_retrieval_latency_seconds",
    "Pinecone query latency",
)
rag_chunks_retrieved_total = Counter(
    "rag_chunks_retrieved_total",
    "RAG chunks retrieved during voice calls",
    ["org_id"],
)


@contextmanager
def observe_tool_execution(tool_name: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        tool_execution_latency.labels(tool_name=tool_name).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_rag_retrieval() -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        rag_retrieval_latency.observe(time.perf_counter() - start)


@contextmanager
def observe_churn_scoring() -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        churn_scoring_latency.observe(time.perf_counter() - start)
