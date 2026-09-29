"""Deterministic extractive provider (offline / tests / demo only).

This provider is **not** a mock. It performs genuine grounded generation: it
parses the retrieved context blocks that the pipeline supplies, scores every
sentence against the user's question with a TF-IDF-ish overlap signal, and
returns the best matching sentences verbatim with real source citations.

Because it only ever quotes retrieved text it cannot invent policy, which makes
it the default provider for local development, CI and the shipped demo. It is
refused when ``APP_ENV=production`` (see :func:`app.rag.generation.llm.provider_factory`).
"""

from __future__ import annotations

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.generation.llm import LLMProvider
from app.rag.retrieval.scorer import distinctive_terms, stem

logger = get_logger(__name__)

_STOPWORDS = frozenset(
    """a an the and or but if then than so at by for with to from of in on as is are was
    were be been being do does did have has had i you he she it we they what which who whom
    whose how why when where about into over under again further once here there all any both
    each few more most other some such no nor not only own same too very can will just should
    now please tell me my i 'm am get does do know explain""".split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CHUNK_HEADER = re.compile(r"^\[(\d+)\]\s+source=(.+?),\s*page=(\d+)\s*$")
_LEADING_DASH = re.compile(r"^[\s\-*\u2022]+")
_WORD = re.compile(r"[a-z0-9']+")
_SENTENCE = re.compile(r"^(.{25,400}?[.!?])\s*$")

MIN_SENTENCE_CHARS = 25
#: "How many paid leave days do I get?" is answered by *two* sentences — the
#: annual entitlement ("18 days of paid annual leave") and the sick entitlement
#: ("10 days of paid sick leave") — which score identically on question overlap.
#: Capping the answer at 3 sentences per source drops whichever one sorts second,
#: silently turning a correct answer into a wrong one.
MAX_SENTENCES = 7
MAX_SENTENCES_PER_SOURCE = 4
#: How many consecutive sentences form a scoring window. Facts are frequently
#: phrased in the sentence *after* the one that names the topic, e.g.
#: "Overtime is not paid." / "Time worked beyond 40 hours is taken back as
#: time off in lieu." Scoring only single sentences would pick the first and drop
#: the sentence that actually contains the answer.
WINDOW = 2
_HEADING = re.compile(r"^\d+[.)]?\s*[A-Z][A-Za-z0-9 ,'’\-/()&]{0,58}$|^[A-Z][A-Za-z0-9 ,'’\-/()&]{0,58}$")
_QUANTITY_QUESTION = re.compile(
    r"\b(how many|how much|how long|what number|what percentage|what is the maximum|"
    r"what is the minimum|maximum number|limit)\b",
    re.IGNORECASE,
)
_UNIT = re.compile(r"\b(days?|weeks?|months?|years?|hours?|minutes?|usd|dollars?|%|percent)\b")
#: A figure attached to its unit, e.g. "18 days", "600 USD", "4%". This is what
#: actually answers "how many days / how much do I get", and it is rare enough in
#: policy prose to be a strong signal.
_NUMBER_BEFORE_UNIT = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:[a-z]+\s+){0,2}?(days?|weeks?|months?|years?|hours?|"
    r"minutes?|usd|dollars?|%|percent)\b",
    re.IGNORECASE,
)


class ExtractiveProvider(LLMProvider):
    """Quotes the most relevant retrieved sentences, with real citations."""

    name = "extractive"

    # -- context parsing -------------------------------------------------
    @staticmethod
    def _strip_headings(body_lines: list[str]) -> list[str]:
        """Drop section headings that survived chunking.

        PDF extraction yields a heading on its own line ("Sick leave"), and the
        assembled context would otherwise glue it onto the first sentence of the
        section: "Sick leave Employees receive 10 days of paid sick leave".
        """
        if len(body_lines) > 1 and _HEADING.match(body_lines[0]):
            candidate = body_lines[0]
            if len(candidate) <= 58 and not candidate.rstrip().endswith((".", "!", "?", ":")):
                return body_lines[1:]
        return body_lines

    def _parse_context(self, context: str) -> list[tuple[str, int, str]]:
        """Split the assembled context into ``(filename, page, sentence)`` triples."""
        passages: list[tuple[str, int, str]] = []
        seen: set[str] = set()

        for block in context.split("\n\n"):
            lines = block.splitlines()
            if not lines:
                continue
            header = _CHUNK_HEADER.match(lines[0].strip())
            if not header:
                continue
            filename, page = header.group(2).strip(), int(header.group(3))
            body_lines = self._strip_headings([line.strip() for line in lines[1:] if line.strip()])
            body = " ".join(body_lines).strip()
            if not body:
                continue

            for raw in _SENTENCE_SPLIT.split(body):
                sentence = _LEADING_DASH.sub("", raw).strip()
                if len(sentence) < MIN_SENTENCE_CHARS:
                    continue
                key = sentence[:80].lower()
                if key in seen:
                    continue
                seen.add(key)
                passages.append((filename, page, sentence))

        return passages

    # -- scoring ---------------------------------------------------------
    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1}

    def _select(
        self, passages: list[tuple[str, int, str]], question: str
    ) -> list[tuple[str, int, str]]:
        """Rank context sentences by how well they answer the question.

        Scoring deliberately reuses :func:`distinctive_terms` — the same signal the
        retriever uses. Counting *all* question words (as a plain bag of words
        would) rewards sentences for echoing filler such as "per year" or "days",
        which in a policy document matches dozens of unrelated sections.
        """
        terms = distinctive_terms(question) or sorted(self._tokens(question))
        if not terms:
            return []

        term_stems = set(terms)
        wants_number = bool(_QUANTITY_QUESTION.search(question))
        units = {u.lower().rstrip("s") for u in _UNIT.findall(question.lower())}

        # --- score sliding windows of consecutive sentences -----------------
        windows: list[tuple[float, int, tuple[tuple[str, int, str], ...]]] = []
        for start in range(len(passages)):
            span = passages[start : start + WINDOW + 1]
            if not span or len({item[0] for item in span}) > 1:
                continue  # never merge sentences across sources
            window_text = " ".join(item[2] for item in span)
            tokens = self._tokens(window_text)
            stems = {stem(token) for token in tokens}
            overlap = {term for term in term_stems if term in tokens or term in stems}

            quantified = bool(_NUMBER_BEFORE_UNIT.search(window_text)) and bool(units)
            if not overlap and not quantified:
                continue

            score = len(overlap) / len(term_stems) + 0.1 * len(overlap)
            if quantified:
                score += 0.35
            windows.append((score, start, tuple(span)))

        windows.sort(key=lambda item: (-item[0], item[1]))

        selected: list[tuple[str, int, str]] = []
        per_source: dict[str, int] = {}
        chosen: set[str] = set()

        def add(passage: tuple[str, int, str]) -> None:
            filename, _, sentence = passage
            if len(selected) >= MAX_SENTENCES or sentence in chosen:
                return
            if per_source.get(filename, 0) >= MAX_SENTENCES_PER_SOURCE:
                return
            per_source[filename] = per_source.get(filename, 0) + 1
            chosen.add(sentence)
            selected.append(passage)

        def rank_sentences(span: tuple[tuple[str, int, str], ...]) -> list[tuple[str, int, str]]:
            """Within a window, quote the most on-topic sentence first."""
            return sorted(
                span,
                key=lambda item: (
                    -len(term_stems & {stem(t) for t in self._tokens(item[2])}),
                    len(item[2]),
                ),
            )

        # Round 1 — one sentence from every strong window, so the answer draws on
        # the whole evidence set before any single document fills the budget. Doing
        # this in a single pass lets the top-ranked chunk's overlapping windows
        # consume the per-source quota and silently drop the sentence that answers
        # the question.
        for _, _, span in windows:
            for passage in rank_sentences(span):
                add(passage)
                break

        # Round 2 — fill the remaining quota from the same windows.
        for _, _, span in windows:
            for passage in rank_sentences(span):
                add(passage)

        # Round 3 — reading order, so the answer still reads as a coherent passage.
        for passage in passages:
            if len(selected) >= MAX_SENTENCES:
                break
            add(passage)

        return selected

    # -- provider API ----------------------------------------------------
    async def complete(self, system: str, user: str) -> str:
        if "RETRIEVED CONTEXT:" not in system:
            logger.warning("extractive: prompt did not contain a context block")
            return settings.NO_CONTEXT_RESPONSE

        context = system.split("RETRIEVED CONTEXT:", 1)[1].strip()
        passages = self._parse_context(context)
        if not passages:
            return settings.NO_CONTEXT_RESPONSE

        question = user.split("Question:", 1)[-1].strip() if "Question:" in user else user
        selected = self._select(passages, question)
        if not selected:
            return settings.NO_CONTEXT_RESPONSE

        lines: list[str] = []
        seen: set[str] = set()
        for filename, page, sentence in selected:
            key = sentence[:60].lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(f'- {sentence} *[{filename}, page {page}]*')

        if not lines:
            return settings.NO_CONTEXT_RESPONSE

        return "According to the HR knowledge base:\n\n" + "\n".join(lines)
