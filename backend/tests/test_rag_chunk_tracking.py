from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.constants import SEED_ORG_ID
from app.core.logging_config import set_call_id
from app.models.call_transcript import CallTranscript
from app.services.transcript_service import TranscriptService
from app.services.tool_executor import ToolExecutor, _build_rag_chunk_metadata


def test_build_rag_chunk_metadata_truncates_preview_to_100_chars():
    metadata = _build_rag_chunk_metadata(
        {
            "chunk_id": "chunk-1",
            "source": "faq.md",
            "similarity_score": 0.87,
            "text": "A" * 150,
            "namespace": "faq_general",
        }
    )

    assert metadata["source"] == "faq.md"
    assert metadata["similarity_score"] == pytest.approx(0.87)
    assert len(metadata["text_preview"]) == 100


@pytest.mark.asyncio
async def test_execute_rag_query_accumulates_chunks_on_executor(
    db_session, mock_rag_retriever
):
    from app.rag.retriever import RAGRetriever
    from app.services.churn_service import ChurnService
    from app.services.customer_service import CustomerService
    from app.services.dispatch_service import DispatchService
    from app.services.ticket_service import TicketService

    call_id = f"rag-track-{uuid.uuid4().hex[:8]}"
    set_call_id(call_id)
    try:
        mock_retriever = AsyncMock(spec=RAGRetriever)
        mock_retriever.retrieve.return_value = [
            {
                "chunk_id": "chunk-a",
                "text": "Filter replacement every 90 days.",
                "source": "maintenance.md",
                "similarity_score": 0.91,
                "namespace": "faq_general",
            }
        ]
        executor = ToolExecutor(
            customer_service=CustomerService(db_session),
            dispatch_service=DispatchService(db_session),
            churn_service=ChurnService(db_session),
            ticket_service=TicketService(db_session),
            rag_retriever=mock_retriever,
        )
        executor.set_tenant(SEED_ORG_ID, org_slug="hvac-demo")

        with patch(
            "app.services.tool_executor._append_rag_chunks_to_cache",
            new_callable=AsyncMock,
        ) as mock_cache_append:
            await executor.execute_rag_query(
                query="filter maintenance",
                namespace="faq_general",
                top_k=1,
            )

        summary = await executor.get_rag_chunks_summary(call_id)
        assert len(summary) == 1
        assert summary[0]["source"] == "maintenance.md"
        assert "Filter replacement" in summary[0]["text_preview"]
        mock_cache_append.assert_awaited_once()
    finally:
        set_call_id("")


@pytest.mark.asyncio
async def test_empty_rag_results_do_not_break_accumulation(db_session):
    from app.rag.retriever import RAGRetriever
    from app.services.churn_service import ChurnService
    from app.services.customer_service import CustomerService
    from app.services.dispatch_service import DispatchService
    from app.services.ticket_service import TicketService

    mock_retriever = AsyncMock(spec=RAGRetriever)
    mock_retriever.retrieve.return_value = []
    executor = ToolExecutor(
        customer_service=CustomerService(db_session),
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=mock_retriever,
    )
    executor.set_tenant(SEED_ORG_ID, org_slug="hvac-demo")

    payload = json.loads(
        await executor.execute_rag_query(
            query="unknown topic",
            namespace="faq_general",
            top_k=3,
        )
    )

    assert payload["success"] is True
    assert payload["data"]["retrieved_context"] == []
    assert await executor.get_rag_chunks_summary() == []


@pytest.mark.asyncio
async def test_process_completed_call_persists_rag_chunks_used(
    db_session, seeded_customer
):
    service = TranscriptService(db_session)
    call_id = f"rag-persist-{uuid.uuid4().hex[:8]}"
    rag_chunks = [
        {
            "chunk_id": "chunk-a",
            "source": "pricing.md",
            "similarity_score": 0.88,
            "text_preview": "Diagnostic fee is $89.",
            "namespace": "pricing",
        }
    ]
    payload = {
        "type": "end-of-call-report",
        "call": {
            "id": call_id,
            "customer": {"number": seeded_customer["phone"]},
            "startedAt": "2026-06-01T12:00:00Z",
            "endedAt": "2026-06-01T12:05:00Z",
        },
        "messages": [
            {"role": "assistant", "message": "Hi, how can I help?"},
            {"role": "user", "message": "What is the diagnostic fee?"},
        ],
    }

    with patch("app.services.transcript_service.publish_call_features", return_value=True):
        result = await service.process_completed_call(
            payload,
            SEED_ORG_ID,
            rag_chunks_used=rag_chunks,
        )
        await db_session.commit()

    assert result is not None
    row = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )
    ).scalar_one()
    assert row.rag_chunks_used == rag_chunks


@pytest.mark.asyncio
async def test_call_end_background_persists_rag_chunks_from_executor(
    db_session, seeded_customer
):
    from app.api.v1.webhook_vapi import _process_call_end_background

    call_id = f"rag-end-{uuid.uuid4().hex[:8]}"
    rag_chunks = [
        {
            "chunk_id": "chunk-b",
            "source": "faq.md",
            "similarity_score": 0.75,
            "text_preview": "Emergency service available 24/7.",
            "namespace": "faq_general",
        }
    ]
    payload = {
        "type": "end-of-call-report",
        "call": {
            "id": call_id,
            "customer": {"number": seeded_customer["phone"]},
            "startedAt": "2026-06-01T12:00:00Z",
            "endedAt": "2026-06-01T12:05:00Z",
        },
        "messages": [
            {"role": "assistant", "message": "Hello."},
            {"role": "user", "message": "Do you offer emergency service?"},
        ],
    }

    mock_executor = AsyncMock()
    mock_executor.get_rag_chunks_summary.return_value = rag_chunks
    mock_executor.clear_rag_chunks_cache = AsyncMock()

    with (
        patch("app.api.v1.webhook_vapi.get_session_factory") as mock_factory,
        patch(
            "app.api.v1.webhook_vapi.deps.build_tool_executor",
            return_value=mock_executor,
        ),
        patch("app.services.transcript_service.publish_call_features", return_value=True),
    ):
        mock_factory.return_value.return_value.__aenter__.return_value = db_session
        mock_factory.return_value.return_value.__aexit__.return_value = None
        await _process_call_end_background(payload, str(SEED_ORG_ID))
        await db_session.commit()

    row = (
        await db_session.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )
    ).scalar_one()
    assert row.rag_chunks_used == rag_chunks
    mock_executor.get_rag_chunks_summary.assert_awaited_once_with(call_id)
    mock_executor.clear_rag_chunks_cache.assert_awaited_once_with(call_id)
