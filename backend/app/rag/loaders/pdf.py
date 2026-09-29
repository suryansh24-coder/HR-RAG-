"""PDF extraction using PyMuPDF (layout-aware, page-numbered)."""

from __future__ import annotations

from dataclasses import asdict

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


def load_document(path: str, filename: str, ext: str) -> ExtractedDocument:
    from app.rag.loaders.markdown import load_markdown
    from app.rag.loaders.text import load_txt

    loader = {".pdf": load_pdf, ".txt": load_txt, ".md": load_markdown, ".markdown": load_markdown}.get(ext)
    if loader is None:
        raise ValidationError(f"Unsupported file extension: {ext}")
    return loader(path, filename)


def page_metadata(document: ExtractedDocument, page_number: int) -> dict:
    """Metadata payload for a chunk originating from a given page."""
    meta = asdict(document.pages[page_number - 1]) if page_number <= len(document.pages) else {}
    return {"page": meta.get("page", page_number)}