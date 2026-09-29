"""Hybrid relevance scoring: vector similarity + lexical coverage.

Why hybrid
----------
Pure vector similarity is a poor *refusal* mechanism. A general-purpose
embedding model will always return its "closest" passage, so an out-of-scope
question such as *"What is the company's stock trading policy?"* still scores
around 0.62 cosine against an HR document. Thresholding on cosine alone
therefore either answers unanswerable questions (hallucination risk) or rejects
legitimate questions.

The fix is to combine two independent signals:

* **cosine similarity** — captures paraphrase and semantic intent.
* **lexical coverage** — the share of the question's *distinctive* terms
  (content words, stem-normalised) that literally appear in the chunk.

The combined score is ``alpha * cosine + (1 - alpha) * coverage``, plus one
gate: a chunk that shares **no** distinctive term with a question that has two or
more is rejected outright — no semantic similarity alone can rescue it.

The gate is lexical, so it behaves predictably. *"What does a competitor pay
their software engineers?"* matches a work-from-home policy on the word *pay*
alone, which is not enough to answer it: the terms *competitor* and *software*
appear nowhere in the corpus, so the honest response is a refusal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Question words, HR boilerplate and filler carry no retrieval signal: they
# appear in almost every document in the corpus and only dilute coverage.
GENERIC_TERMS = frozenset(
    """a an the and or but if then than so at by for with to from of in on as is are was were
    be been being do does did doing have has had having i me my we our us you your he she it
    they them their this that these those what which who whom whose how why when where who
    about into over under again further once here there all any both each few more most other
    some such no nor not only own same too very can could would should shall may might must
    will do now please tell give show list explain detail details information info regarding
    related available options option thing things stuff get know need want say says
    company companies organisation organization hr nexus assistant
    employee employees employ employed employer employment staff team member members
    policy policies procedure procedures rule rules guideline guidelines standard standards
    work working works worked job role position day days week weeks month months year years
    time times hour hours minute minutes date dates many much lot lots number
    per via using use used""".split()
)

_WORD = re.compile(r"[a-z0-9]+")

#: Plural / third-person-singular endings, longest first.
_PLURALS: tuple[tuple[str, str], ...] = (
    ("sses", "ss"),
    ("ies", "y"),
    ("ches", "ch"),
    ("shes", "sh"),
    ("xes", "x"),
    ("zes", "z"),
    ("ses", "s"),
    ("es", ""),
    ("s", ""),
)
#: Verb / noun derivational endings, longest first.
_DERIVATIVES: tuple[str, ...] = ("ational", "ization", "isation", "ation", "ement", "ments", "ment", "ness", "ity", "ing", "ers", "er", "ed")
#: A stem only fuzzy-matches a longer token when it is at least this long, so
#: ``over`` never matches ``overtime`` and ``comp`` never matches ``company``.
_MIN_FUZZY_STEM = 5


def stem(token: str) -> str:
    """Light, suffix-stripping normaliser.

    A naive 4-character prefix is *not* usable for English: ``overtime`` and
    ``over``, ``competitor`` and ``company``, ``resign`` and ``resignation`` all
    collapse onto the same prefix, so unrelated documents score as matches.
    Stripping known endings keeps the discriminative part of the word instead.
    """
    for suffix, replacement in _PLURALS:
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            token = token[: -len(suffix)] + replacement
            break

    for suffix in _DERIVATIVES:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break

    return token


def terms_match(term: str, tokens: set[str], stems: set[str]) -> bool:
    """Does a query term occur in the chunk, allowing derivational variants?"""
    if term in stems or term in tokens:
        return True
    if len(term) < _MIN_FUZZY_STEM:
        return False
    return any(token.startswith(term) for token in tokens)


def distinctive_terms(question: str) -> list[str]:
    """Stemmed, de-duplicated content words of the question, order preserved."""
    seen: dict[str, None] = {}
    for token in _WORD.findall(question.lower()):
        if len(token) < 3 or token in GENERIC_TERMS:
            continue
        seen.setdefault(stem(token), None)
    return list(seen)


def _haystack(text: str) -> tuple[set[str], set[str]]:
    tokens = {token for token in _WORD.findall(text.lower()) if len(token) >= 3}
    return tokens, {stem(token) for token in tokens}


@dataclass(frozen=True)
class LexicalMatch:
    coverage: float
    matched: int
    total: int

    @property
    def has_no_signal(self) -> bool:
        """True when the question is specific but the chunk shares nothing with it."""
        return self.total >= 2 and self.matched == 0


def lexical_match(question_terms: list[str], text: str) -> LexicalMatch:
    if not question_terms:
        return LexicalMatch(coverage=1.0, matched=0, total=0)

    tokens, stems = _haystack(text)
    matched = sum(1 for term in question_terms if terms_match(term, tokens, stems))
    return LexicalMatch(
        coverage=matched / len(question_terms), matched=matched, total=len(question_terms)
    )


def corpus_coverage(question_terms: list[str], known_terms: frozenset[str] | set[str]) -> float:
    """Share of the question's distinctive terms that exist *anywhere* in the corpus.

    A question whose subject the knowledge base has never seen cannot be answered
    no matter how close a chunk happens to be — "What is the CEO's home address?"
    lands on the work-from-home policy because that document also mentions a
    "home" and an "address". Refusing on corpus coverage is the difference between
    admitting ignorance and quoting an unrelated policy as though it were the
    answer.
    """
    if not question_terms:
        return 1.0
    return sum(1 for term in question_terms if term in known_terms) / len(question_terms)


def hybrid_score(
    cosine: float,
    coverage: float,
    alpha: float = 0.65,
) -> float:
    """Blend semantic and lexical relevance into a single comparable score."""
    return round(alpha * cosine + (1.0 - alpha) * coverage, 6)
