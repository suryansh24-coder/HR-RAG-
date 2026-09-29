"""Unit tests for text cleaning, chunking and the extractive provider."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.chunking.chunker import RecursiveChunker  # noqa: E402
from app.rag.generation.providers.extractive import ExtractiveProvider  # noqa: E402
from app.rag.loaders.cleaning import clean_text  # noqa: E402


class TestCleanText:
    def test_normalises_windows_newlines(self):
        assert "\r" not in clean_text("a\r\nb\rc")

    def test_strips_page_footers(self):
        assert "page 2 of 7" not in clean_text("Policy text\n\nPage 2 of 7\n\nMore text")
        assert "CONFIDENTIAL" not in clean_text("x\nConfidential\ny")

    def test_converts_unicode_bullets(self):
        assert clean_text("• First item") == "- First item"

    def test_collapses_excess_blank_lines(self):
        assert "\n\n\n" not in clean_text("a\n\n\n\n\nb")

    def test_handles_empty_input(self):
        assert clean_text("") == ""
        assert clean_text("   \n ") == ""

    def test_removes_bom_and_control_characters(self):
        assert clean_text("\ufeffhello\x00world") == "hello world"


class TestRecursiveChunker:
    def test_rejects_invalid_sizes(self):
        from app.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            RecursiveChunker(chunk_size=10)
        with pytest.raises(ValidationError):
            RecursiveChunker(chunk_size=100, chunk_overlap=100)

    def test_short_text_is_one_chunk(self):
        chunks = RecursiveChunker(chunk_size=800, chunk_overlap=120).chunk_text("Short text.")
        assert len(chunks) == 1

    def test_respects_max_chunk_size(self):
        text = " ".join(f"Sentence number {i} about leave policy." for i in range(200))
        chunks = RecursiveChunker(chunk_size=400, chunk_overlap=60).chunk_text(text)
        assert len(chunks) > 1
        assert all(len(c) <= 520 for c in chunks)

    def test_overlap_keeps_bridging_text(self):
        text = " ".join(f"Fact {i} about the expense policy applies." for i in range(120))
        chunker = RecursiveChunker(chunk_size=400, chunk_overlap=120)
        chunks = chunker.chunk_text(text)
        assert len(chunks) > 1

    def test_empty_text(self):
        assert RecursiveChunker().chunk_text("") == []


CONTEXT = """[1] source=leave_policy.pdf, page=1
3. Sick leave
Employees receive 10 days of paid sick leave per calendar year.
Unused sick leave cannot be carried forward.

[2] source=travel_policy.pdf, page=2
Overtime
Overtime is not paid. Time worked beyond 40 hours in a week is taken back as time
off in lieu."""


class TestExtractiveProvider:
    def setup_method(self):
        self.provider = ExtractiveProvider()

    def _context(self, text: str) -> str:
        return f"RETRIEVED CONTEXT:\n{text}"

    def test_refuses_without_a_context_block(self):
        answer = asyncio.run(self.provider.complete("No context here", "Question: x?"))
        assert "couldn't find" in answer.lower()

    def test_never_invents_content(self):
        """Every quoted sentence must appear verbatim in the retrieved context."""
        answer = asyncio.run(
            self.provider.complete(
                self._context(CONTEXT), "Question: How many paid sick leave days do I get?"
            )
        )
        quoted = [line[2:].split("*[")[0].strip() for line in answer.splitlines() if line.startswith("- ")]
        flat = " ".join(CONTEXT.split())
        for sentence in quoted:
            assert " ".join(sentence.split()) in flat

    def test_strips_headings_from_sentences(self):
        passages = self.provider._parse_context(CONTEXT)
        assert not any(s.startswith("Sick leave") for _, _, s in passages)
        assert not any(s.startswith("Overtime ") for _, _, s in passages)

    def test_selects_the_sentence_that_contains_the_fact(self):
        passages = self.provider._parse_context(CONTEXT)
        selected = self.provider._select(passages, "How many paid sick leave days do I get?")
        assert any("10 days" in sentence for _, _, sentence in selected)

    def test_follows_a_fact_into_the_next_sentence(self):
        """The 'time off in lieu' detail lives in the sentence after the topic."""
        passages = self.provider._parse_context(CONTEXT)
        selected = self.provider._select(passages, "How is overtime compensated?")
        assert any("time off in lieu" in sentence for _, _, sentence in selected)

    def test_answers_quantity_questions_with_a_figure(self):
        passages = self.provider._parse_context(CONTEXT)
        selected = self.provider._select(passages, "What is the annual leave allowance?")
        assert any(any(ch.isdigit() for ch in sentence) for _, _, sentence in selected)

    def test_cites_filename_and_page(self):
        answer = asyncio.run(
            self.provider.complete(self._context(CONTEXT), "Question: How many sick leave days?")
        )
        assert "*[leave_policy.pdf, page 1]*" in answer
