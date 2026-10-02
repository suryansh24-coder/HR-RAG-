"""PDF extraction using PyMuPDF (layout-aware, page-numbered)."""

from __future__ import annotations

from pymupdf import Document, EmptyFileError

from app.core.exceptions import ValidationError
from app.rag.loaders.base import ExtractedDocument, ExtractedPage


def load_pdf(path: str, filename: str) -> ExtractedDocument:
    try:
        document = Document(path)
    except EmptyFileError as exc:
        raise ValidationError(f"PDF '{filename}' appears to be empty or corrupt.") from exc
    except Exception as exc:  # noqa: BLE001 - pymupdf raises several error types
        raise ValidationError(f"Could not open PDF '{filename}': {exc}") from exc

    try:
        if document.page_count == 0:
            raise ValidationError(f"PDF '{filename}' contains no pages.")

        pages: list[ExtractedPage] = []
        for index, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()
            pages.append(ExtractedPage(text=text, page=index))

        content = "\n\n".join(p.text for p in pages).strip()

        if not content:
            raise ValidationError(
                f"PDF '{filename}' contains no extractable text "
                "(it may be a scanned image-only document)."
            )
    finally:
        document.close()

    return ExtractedDocument(
        filename=filename, document_type="pdf", content=content, pages=pages
    )