"""Plain text extraction for .txt files."""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.rag.loaders.base import ExtractedDocument, ExtractedPage


def load_txt(path: str, filename: str) -> ExtractedDocument:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError as exc:
        raise ValidationError(f"Could not read text file: {exc}") from exc

    content = raw.strip()
    if not content:
        raise ValidationError(f"Document '{filename}' is empty.")

    pages = [ExtractedPage(text=content, page=1)]
    return ExtractedDocument(
        filename=filename, document_type="txt", content=content, pages=pages
    )