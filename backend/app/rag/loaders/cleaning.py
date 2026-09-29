"""Text cleaning: normalise whitespace, unicode bullets, PDF artefacts."""

from __future__ import annotations

import re
import unicodedata

_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_NEWLINES = re.compile(r"\n{3,}")
_BULLET = re.compile(r"^[\u2022\u2023\u25aa\u25cf\-\*\u2013\u2014]\s+", re.MULTILINE)
_PAGE_FOOTERS = re.compile(
    r"(?mi)^\s*(page\s+\d+\s*(of\s+\d+)?|confidential|draft\s*[-–—]?\s*internal)\s*$"
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(text: str) -> str:
    """Normalise raw extracted text so chunking and embedding see clean input."""
    if not text:
        return ""

    text = text.replace("\ufeff", "")
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHARS.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _PAGE_FOOTERS.sub("", text)
    text = _BULLET.sub("- ", text)
    text = _NEWLINES.sub("\n\n", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


def clean_page_text(text: str) -> str:
    return clean_text(text)
