#!/usr/bin/env python3
"""Index active service catalog entries into the pricing RAG namespace (idempotent)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from app.core.constants import SEED_ORG_ID  # noqa: E402
from app.core.database import get_session_factory  # noqa: E402
from app.models.service_catalog import ServiceCatalog  # noqa: E402
from app.rag.indexer import KnowledgeIndexer  # noqa: E402
from app.services.knowledge_service import KnowledgeService  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Index service catalog into pricing RAG")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force local mock vector store (no Pinecone/OpenAI keys required)",
    )
    args = parser.parse_args()

    indexer = KnowledgeIndexer(force_mock=args.mock)
    total = 0
    async with get_session_factory()() as session:
        knowledge = KnowledgeService(session, indexer=indexer)
        faq_count = await knowledge.index_pricing_faq(SEED_ORG_ID)
        total += faq_count
        print(f"Indexed pricing FAQ ({faq_count} chunk(s)).")

        rows = (
            await session.execute(
                select(ServiceCatalog).where(
                    ServiceCatalog.org_id == SEED_ORG_ID,
                    ServiceCatalog.is_active.is_(True),
                )
            )
        ).scalars().all()

        for row in rows:
            count = await knowledge.index_service_to_pricing(row)
            total += count
            print(f"  pricing::{row.service_code} -> {count} chunk(s)")

        await session.commit()
    print(f"Done. {total} total chunk(s) indexed into pricing namespace.")


if __name__ == "__main__":
    asyncio.run(main())
