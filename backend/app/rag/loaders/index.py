"""Document loader facade: format detection + extraction + cleaning."""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.rag.loaders.base import ExtractedDocument, ExtractedPage
from app.rag.loaders.cleaning import clean_page_text


def extract_and_clean(path: str, filename: str, ext: str) -> ExtractedDocument:
    from app.rag.loaders.markdown import load_markdown
    from app.rag.loaders.pdf import load_pdf
    from app.rag.loaders.text import load_txt

    if ext == ".pdf":
        doc = load_pdf(path, filename)
    elif ext == ".txt":
        doc = load_txt(path, filename)
    elif ext in (".md", ".markdown"):
        doc = load_markdown(path, filename)
    else:
        raise ValidationError(f"Unsupported file extension: {ext}")

    doc.pages = [ExtractedPage(text=clean_page_text(p.text), page=p.page) for p in doc.pages]
    doc.content = "\n\n".join(p.text for p in doc.pages if p.text).strip()
    return doc