from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    source: str
    namespace: str
    chunk_index: int
    equipment_model: str | None = None


def split_text(
    text: str,
    source: str,
    namespace: str,
    equipment_model: str | None = None,
) -> list[DocumentChunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    parts = splitter.split_text(text)
    return [
        DocumentChunk(
            text=part,
            source=source,
            namespace=namespace,
            chunk_index=index,
            equipment_model=equipment_model,
        )
        for index, part in enumerate(parts)
    ]


def split_markdown_file(
    path: Path,
    namespace: str,
    equipment_model: str | None = None,
) -> list[DocumentChunk]:
    content = path.read_text(encoding="utf-8")
    return split_text(
        text=content,
        source=str(path),
        namespace=namespace,
        equipment_model=equipment_model,
    )


def split_by_paragraph(
    text: str,
    source: str,
    namespace: str,
    equipment_model: str | None = None,
) -> list[DocumentChunk]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts:
        return []
    return [
        DocumentChunk(
            text=part,
            source=source,
            namespace=namespace,
            chunk_index=index,
            equipment_model=equipment_model,
        )
        for index, part in enumerate(parts)
    ]


_PAGE_BREAK_MARKER = "\n--- PAGE BREAK ---\n"


def split_by_page_breaks(
    text: str,
    source: str,
    namespace: str,
    equipment_model: str | None = None,
) -> list[DocumentChunk]:
    parts = [p.strip() for p in text.split(_PAGE_BREAK_MARKER) if p.strip()]
    if not parts:
        return split_by_paragraph(text, source, namespace, equipment_model)
    return [
        DocumentChunk(
            text=part,
            source=source,
            namespace=namespace,
            chunk_index=index,
            equipment_model=equipment_model,
        )
        for index, part in enumerate(parts)
    ]


def chunk_text(
    text: str,
    *,
    source: str,
    namespace: str,
    strategy: str = "paragraph",
    equipment_model: str | None = None,
) -> list[DocumentChunk]:
    normalized = (strategy or "paragraph").lower()
    if normalized == "fixed":
        return split_text(text, source, namespace, equipment_model)
    if normalized == "page":
        return split_by_page_breaks(text, source, namespace, equipment_model)
    return split_by_paragraph(text, source, namespace, equipment_model)
