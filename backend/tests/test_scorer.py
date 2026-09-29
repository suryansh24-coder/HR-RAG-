"""Unit tests for the pure retrieval/scoring logic (no models, no Qdrant)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.retrieval.scorer import (  # noqa: E402
    corpus_coverage,
    distinctive_terms,
    hybrid_score,
    lexical_match,
    stem,
    terms_match,
)

LEAVE_TEXT = (
    "Every full-time employee receives 18 days of paid annual leave per completed "
    "calendar year. Up to 5 unused days of annual leave may be carried forward into "
    "the following calendar year."
)
WFH_TEXT = (
    "Hybrid employees must be present in the office 3 days per week. Each "
    "remote-eligible employee receives a one-time home office budget of 600 USD."
)


class TestStem:
    def test_strips_plural_s(self):
        assert stem("policies") == "policy"
        assert stem("benefits") == "benefit"
        assert stem("days") == "day"

    def test_unifies_derivations_through_matching(self):
        """Stems are only equal when the suffix is identical.

        ``compensated`` and ``compensation`` normalise differently, but they must
        still match the same chunk — that is what ``terms_match`` guarantees, and
        it is the contract retrieval actually depends on.
        """
        assert stem("compensated") != stem("compensation")
        assert terms_match(stem("compensated"), {"compensation"}, {stem("compensation")})
        assert terms_match(stem("resigning"), {"resignation"}, {stem("resignation")})

    def test_does_not_collide_unrelated_words(self):
        """A 4-character prefix stemmer merges these; a suffix stripper must not."""
        assert stem("overtime") != stem("over")
        assert stem("competitor") != stem("company")
        assert stem("office") != stem("official")

    def test_keeps_short_words_intact(self):
        assert stem("ceo") == "ceo"
        assert stem("pay") == "pay"


class TestDistinctiveTerms:
    def test_drops_question_words_and_hr_boilerplate(self):
        terms = distinctive_terms("How many paid leave days do I get per year?")
        assert terms == ["paid", "leave"]

    def test_keeps_content_words(self):
        terms = distinctive_terms("What is the maternity leave entitlement?")
        assert stem("maternity") in terms
        assert stem("leave") in terms
        assert stem("entitlement") in terms
        assert "what" not in terms and "the" not in terms

    def test_deduplicates_after_stemming(self):
        terms = distinctive_terms("leave policy and leave policies")
        assert terms.count(stem("leave")) == 1


class TestLexicalMatch:
    def test_full_coverage(self):
        match = lexical_match(distinctive_terms("How many paid leave days do I get?"), LEAVE_TEXT)
        assert match.coverage == 1.0
        assert match.has_no_signal is False

    def test_no_signal_when_question_is_specific(self):
        match = lexical_match(
            distinctive_terms("What is the competitor salary benchmark?"), WFH_TEXT
        )
        assert match.has_no_signal is True
        assert match.coverage == 0.0

    def test_partial_match_is_not_a_refusal(self):
        """One incidental word is a weak signal, not an answerable question."""
        match = lexical_match(distinctive_terms("What is the CEO home address?"), WFH_TEXT)
        assert match.matched == 1
        assert match.has_no_signal is False

    def test_empty_question_terms_is_not_a_refusal(self):
        """A question with no content words must not be treated as unanswerable."""
        match = lexical_match([], WFH_TEXT)
        assert match.coverage == 1.0
        assert match.has_no_signal is False

    def test_partial_coverage(self):
        match = lexical_match(distinctive_terms("maternity leave"), LEAVE_TEXT)
        assert 0 < match.coverage < 1


class TestTermsMatch:
    def test_fuzzy_match_requires_five_characters(self):
        tokens = {"overtime"}
        stems = {stem("overtime")}
        assert terms_match("over", tokens, stems) is False
        assert terms_match("overtime", tokens, stems) is True

    def test_prefix_match_for_longer_stems(self):
        tokens = {"compensation"}
        assert terms_match(stem("compensated"), tokens, {stem("compensation")}) is True


class TestHybridScore:
    def test_blends_cosine_and_coverage(self):
        assert hybrid_score(0.8, 1.0, alpha=0.65) == pytest.approx(0.87)
        assert hybrid_score(0.8, 0.0, alpha=0.65) == pytest.approx(0.52)

    def test_high_coverage_lifts_a_weak_vector_match(self):
        assert hybrid_score(0.55, 1.0) > hybrid_score(0.55, 0.0)


class TestCorpusCoverage:
    def test_reports_unknown_terms(self):
        known = {"leave", "policy", "pay"}
        assert corpus_coverage(["leave", "pay"], known) == 1.0
        assert corpus_coverage(["leave", "competitor"], known) == 0.5
        assert corpus_coverage(["ceo"], known) == 0.0

    def test_empty_question_is_fully_covered(self):
        assert corpus_coverage([], {"anything"}) == 1.0
