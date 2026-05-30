#!/usr/bin/env python3
"""
Index HVAC knowledge sources into Pinecone or the local mock vector store.

Usage:
  python scripts/index_knowledge_base.py --namespace faq_general --source data/knowledge/faqs/
  python scripts/index_knowledge_base.py --namespace faq_general --source data/knowledge/faqs/ --mock

Spec: RecursiveCharacterTextSplitter chunk_size=512, overlap=64.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.constants import RAG_NAMESPACES
from app.rag.indexer import KnowledgeIndexer


async def main() -> None:
    parser = argparse.ArgumentParser(description="Index HVAC knowledge base")
    parser.add_argument(
        "--namespace",
        required=True,
        choices=sorted(RAG_NAMESPACES),
        help="Pinecone / mock namespace",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Directory or file path to index",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force local mock vector store (no Pinecone/OpenAI keys required)",
    )
    parser.add_argument(
        "--pattern",
        default="*.md",
        help="Glob pattern when source is a directory (default: *.md)",
    )
    args = parser.parse_args()

    source = args.source if args.source.is_absolute() else PROJECT_ROOT / args.source
    indexer = KnowledgeIndexer(project_root=PROJECT_ROOT, force_mock=args.mock)

    if source.is_dir():
        count = await indexer.index_directory(source, namespace=args.namespace, pattern=args.pattern)
    elif source.is_file():
        count = await indexer.index_text_file(source, namespace=args.namespace)
    else:
        raise FileNotFoundError(f"Source not found: {source}")

    backend = "mock file" if indexer.uses_mock else "Pinecone"
    print(f"Indexed {count} chunks into namespace '{args.namespace}' via {backend}.")


if __name__ == "__main__":
    asyncio.run(main())
