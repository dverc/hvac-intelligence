from __future__ import annotations

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
