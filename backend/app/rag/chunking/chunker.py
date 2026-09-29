"""Recursive text chunking with configurable size and overlap.

Chunking strategy
-----------------
* Split the text hierarchically: paragraphs first, then sentences, then words.
* Respect a maximum ``CHUNK_SIZE`` (character count) and slide with a fixed
  ``CHUNK_OVERLAP`` between consecutive chunks so that cut boundaries do not
  lose meaning.
* Chunk boundaries never split a single sentence when avoidable.

Defaults (``CHUNK_SIZE=800``, ``CHUNK_OVERLAP=120``) were chosen because:

* Embedding models such as ``bge-small`` perform best on 1-3 sentence blocks.
* Chunks of ~800 characters map to roughly 120-180 tokens - comfortably inside
  most embedding context windows while retaining enough policy detail for the
  LLM to answer with citations.
* A 120-character overlap (~15%) keeps pronouns/context bridges between chunks,
  improving retrieval for questions that span a boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ValidationError

SENTENCE_BOUNDARIES = ".!?:\n"


@dataclass
class Chunk:
    text: str
    index: int
    metadata: dict


class RecursiveChunker:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
        if chunk_size < 100:
            raise ValidationError("CHUNK_SIZE must be at least 100 characters.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValidationError("CHUNK_OVERLAP must be in [0, CHUNK_SIZE).")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_paragraphs(self, text: str) -> list[str]:
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        # Without this guard, empty input falls through to [text.strip()] and the
        # caller embeds an empty chunk — a zero-information vector that can still
        # win a similarity search.
        return blocks

    def _split_long(self, block: str) -> list[str]:
        if len(block) <= self.chunk_size:
            return [block]
        sentences = self._split_sentences(block)
        parts: list[str] = []
        current = ""
        for sentence in sentences:
            if current and len(current) + len(sentence) + 1 > self.chunk_size:
                if len(current) <= self.chunk_size:
                    parts.append(current)
                else:
                    parts.extend(self._word_split_large(current))
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence
        if current:
            if len(current) <= self.chunk_size:
                parts.append(current)
            else:
                parts.extend(self._word_split_large(current))
        return [p for p in parts if p]

    def _split_sentences(self, block: str) -> list[str]:
        sentences: list[str] = []
        buffer = ""
        for char in block:
            buffer += char
            if char in SENTENCE_BOUNDARIES:
                if buffer.strip():
                    sentences.append(buffer.strip())
                buffer = ""
        if buffer.strip():
            sentences.append(buffer.strip())
        return sentences

    def _word_split_large(self, text: str) -> list[str]:
        words = text.split()
        parts: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > self.chunk_size:
                if current:
                    parts.append(current)
                current = word
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts

    def chunk_text(self, text: str) -> list[str]:
        """Main entry point. Returns list of chunk texts for one page."""

        def candidates() -> list[str]:
            out: list[str] = []
            for block in self.split_paragraphs(text):
                out.extend(self._split_long(block))
            return out

        raw = candidates()
        if not raw:
            return []

        chunks: list[str] = []
        cursor = 0
        while cursor < len(raw):
            group = raw[cursor]
            length = len(group)
            nxt = cursor + 1
            while nxt < len(raw) and length + len(raw[nxt]) + 1 <= self.chunk_size:
                group += "\n\n" + raw[nxt]
                length += len(raw[nxt]) + 1
                nxt += 1
            chunks.append(group)
            cursor = nxt

        return self._apply_overlap(chunks)

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        if self.chunk_overlap == 0 or len(chunks) <= 1:
            return chunks
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            previous = chunks[i - 1]
            bridge = previous[max(0, len(previous) - self.chunk_overlap):].strip()
            overlapped.append((bridge + "\n\n" + chunks[i]).strip())
        return overlapped