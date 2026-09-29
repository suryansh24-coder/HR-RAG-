"""Shared primitives for document loaders."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedPage:
    text: str
    page: int


@dataclass
class ExtractedDocument:
    filename: str
    document_type: str
    content: str
    pages: list[ExtractedPage] = field(default_factory=list)

    @property
    def character_count(self) -> int:
        return len(self.content)