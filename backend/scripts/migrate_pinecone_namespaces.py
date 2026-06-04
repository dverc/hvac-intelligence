#!/usr/bin/env python3
"""
Re-index mock/Pinecone vectors under org-prefixed namespaces (idempotent).

Migrates flat namespaces (e.g. faq_general) to hvac-demo::faq_general for the
seed organization. Safe to run multiple times.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.constants import SEED_ORG_ID  # noqa: E402
from app.rag.constants import RAG_NAMESPACES, get_base_namespace, get_namespace  # noqa: E402
from app.rag.indexer import KnowledgeIndexer  # noqa: E402


SEED_SLUG = "hvac-demo"


async def migrate_mock(indexer: KnowledgeIndexer, *, dry_run: bool) -> int:
    assert indexer._mock_store is not None
    store = indexer._mock_store
    migrated = 0
    new_records: list[dict] = []
    seen_ids: set[str] = set()

    for record in list(store._records):
        ns = record.get("namespace") or ""
        base = get_base_namespace(ns)
        if base not in RAG_NAMESPACES:
            new_records.append(record)
            continue
        if ns.startswith(f"{SEED_SLUG}::"):
            new_records.append(record)
            continue

        target_ns = get_namespace(SEED_SLUG, base)
        updated = dict(record)
        updated["namespace"] = target_ns
        meta = dict(updated.get("metadata") or {})
        meta["namespace"] = target_ns
        updated["metadata"] = meta

        if updated["id"] in seen_ids:
            continue
        seen_ids.add(updated["id"])
        new_records.append(updated)
        migrated += 1

    if not dry_run and migrated:
        store._records = new_records
        store.save()
    return migrated


async def migrate_pinecone(indexer: KnowledgeIndexer, *, dry_run: bool) -> int:
    if indexer._use_mock or indexer._pinecone_index is None:
        return 0

    migrated = 0
    index = indexer._pinecone_index
    stats = index.describe_index_stats()
    ns_stats = getattr(stats, "namespaces", None) or {}

    for flat_ns in RAG_NAMESPACES:
        if flat_ns not in ns_stats:
            continue
        prefixed = get_namespace(SEED_SLUG, flat_ns)
        if prefixed in ns_stats:
            continue

        print(f"Pinecone: migrate {flat_ns} -> {prefixed} (manual re-index may be required)")
        if dry_run:
            migrated += 1
            continue
        # Serverless list/fetch migration is index-specific; mock path is primary for dev.
        migrated += 1

    return migrated


async def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate RAG namespaces to org-prefixed keys")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Force mock store")
    args = parser.parse_args()

    indexer = KnowledgeIndexer(force_mock=args.mock)
    mock_count = await migrate_mock(indexer, dry_run=args.dry_run)
    pine_count = await migrate_pinecone(indexer, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "org_id": str(SEED_ORG_ID),
                "org_slug": SEED_SLUG,
                "mock_records_migrated": mock_count,
                "pinecone_namespaces_flagged": pine_count,
                "dry_run": args.dry_run,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
