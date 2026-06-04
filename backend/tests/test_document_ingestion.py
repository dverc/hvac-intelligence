from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.chunker import chunk_text
from app.services.knowledge_service import _extract_text


def test_pdf_extracts_text_with_page_breaks():
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Page one text"
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page, mock_page]

    with patch("pypdf.PdfReader", return_value=mock_reader):
        text, warnings = _extract_text("manual.pdf", b"%PDF-fake")
    assert "Page one text" in text
    assert "--- PAGE BREAK ---" in text
    assert warnings == []


def test_word_document_extracts_paragraphs():
    mock_paragraph = MagicMock()
    mock_paragraph.text = "Hello from Word"
    mock_paragraph.style.name = "Normal"
    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_paragraph]
    mock_doc.tables = []

    with patch("docx.Document", return_value=mock_doc):
        text, _ = _extract_text("policy.docx", b"PK-fake")
    assert "Hello from Word" in text


def test_unknown_file_type_raises_clear_error():
    with pytest.raises(ValueError, match="Unsupported file type"):
        _extract_text("archive.zip", b"data")


def test_csv_upload_rejected_with_helpful_message():
    with pytest.raises(ValueError, match="CSV files cannot be uploaded"):
        _extract_text("data.csv", b"a,b\n1,2")


def test_chunking_strategies_produce_different_counts():
    text = "Para one.\n\nPara two.\n\nPara three."
    paragraph_chunks = chunk_text(
        text, source="t.txt", namespace="faq_general", strategy="paragraph"
    )
    fixed_chunks = chunk_text(
        text, source="t.txt", namespace="faq_general", strategy="fixed"
    )
    page_text = "Page A\n--- PAGE BREAK ---\nPage B"
    page_chunks = chunk_text(
        page_text, source="t.pdf", namespace="faq_general", strategy="page"
    )
    assert len(paragraph_chunks) == 3
    assert len(page_chunks) == 2
    assert len(fixed_chunks) >= 1
