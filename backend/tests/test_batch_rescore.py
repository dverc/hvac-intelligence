from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import SEED_ORG_ID
from app.pipeline.tasks import (
    _RESCORE_CHUNK_SIZE,
    _chunk_customer_ids,
    _dispatch_parallel_org_rescore,
    batch_rescore_customers,
    rescore_customers_chunk,
)


def test_chunk_customer_ids_splits_into_fifty_customer_batches():
    customer_ids = [f"cust-{index}" for index in range(120)]

    chunks = _chunk_customer_ids(customer_ids)

    assert len(chunks) == 3
    assert len(chunks[0]) == _RESCORE_CHUNK_SIZE
    assert len(chunks[1]) == _RESCORE_CHUNK_SIZE
    assert len(chunks[2]) == 20


def test_dispatch_parallel_org_rescore_queues_correct_chunk_count():
    org_id = str(SEED_ORG_ID)
    customer_ids = [str(uuid.uuid4()) for _ in range(120)]
    mock_group = MagicMock()
    mock_chord = MagicMock()
    mock_workflow = MagicMock()
    mock_chord.return_value = mock_workflow

    with (
        patch("celery.group", mock_group),
        patch("celery.chord", mock_chord),
        patch(
            "app.pipeline.tasks.rescore_customers_chunk.s",
            side_effect=lambda org, chunk: ("chunk-task", org, chunk),
        ),
        patch(
            "app.pipeline.tasks.on_batch_rescore_complete.s",
            return_value=("callback", org_id, 2),
        ),
    ):
        result = _dispatch_parallel_org_rescore(org_id, customer_ids, critical_before=2)

    assert result["chunks"] == 3
    assert result["customers"] == 120
    assert result["mode"] == "parallel"
    mock_group.assert_called_once()
    chunk_tasks = list(mock_group.call_args[0][0])
    assert len(chunk_tasks) == 3
    mock_chord.assert_called_once()
    mock_workflow.apply_async.assert_called_once()


def test_batch_rescore_customers_inline_for_small_org(
    sync_db_session, seeded_sync_customer, monkeypatch
):
    org_id = str(SEED_ORG_ID)
    customer_id = seeded_sync_customer["customer_id"]
    publish_mock = MagicMock()
    monkeypatch.setattr("app.pipeline.tasks.publish_batch_score_complete_sync", publish_mock)

    with (
        patch("app.pipeline.tasks.get_sync_session", return_value=sync_db_session),
        patch(
            "app.pipeline.tasks._group_active_customers_by_org",
            return_value={org_id: [customer_id]},
        ),
        patch("app.pipeline.tasks._dispatch_parallel_org_rescore") as mock_dispatch,
    ):
        result = batch_rescore_customers.run()

    assert result["status"] == "ok"
    assert result["mode"] == "inline"
    assert result["accounts_scored"] == 1
    mock_dispatch.assert_not_called()
    publish_mock.assert_called_once()


def test_rescore_customers_chunk_scores_all_customers_in_chunk(
    sync_db_session, seeded_sync_customer, monkeypatch
):
    org_id = str(SEED_ORG_ID)
    customer_id = seeded_sync_customer["customer_id"]
    monkeypatch.setattr("app.pipeline.tasks.get_sync_session", lambda: sync_db_session)

    result = rescore_customers_chunk.run(org_id, [customer_id])

    assert result["status"] == "ok"
    assert result["customer_count"] == 1
    assert result["accounts_scored"] == 1
    assert result["scoring_errors"] == 0


def test_batch_rescore_customers_dispatches_chunks_for_large_org(monkeypatch):
    org_id = str(SEED_ORG_ID)
    customer_ids = [str(uuid.uuid4()) for _ in range(120)]
    mock_session = MagicMock()

    with (
        patch("app.pipeline.tasks.get_sync_session", return_value=mock_session),
        patch(
            "app.pipeline.tasks._group_active_customers_by_org",
            return_value={org_id: customer_ids},
        ),
        patch("app.pipeline.tasks._count_tier", return_value=0),
        patch("app.pipeline.tasks._score_customers_in_session") as mock_score,
        patch("app.pipeline.tasks._dispatch_parallel_org_rescore") as mock_dispatch,
    ):
        mock_dispatch.return_value = {
            "org_id": org_id,
            "mode": "parallel",
            "customers": 120,
            "chunks": 3,
        }
        result = batch_rescore_customers.run()

    mock_score.assert_not_called()
    mock_dispatch.assert_called_once_with(org_id, customer_ids, 0)
    assert result["status"] == "ok"
    assert result["mode"] == "parallel"
    assert result["orgs"][0]["chunks"] == 3
