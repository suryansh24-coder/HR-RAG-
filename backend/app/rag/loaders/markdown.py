"""Markdown extraction for .md files (plain text with headers kept)."""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.rag.loaders.base import ExtractedDocument, ExtractedPage
from app.rag.loaders.text import load_txt


def load_markdown(path: str, filename: str) -> ExtractedDocument:
    doc: ExtractedDocument = load_txt(path, filename)
    doc.document_type = "md"
    return doc