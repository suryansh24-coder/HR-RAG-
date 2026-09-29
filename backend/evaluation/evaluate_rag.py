#!/usr/bin/env python
"""RAG retrieval + grounded-answer evaluation harness.

Measures, against the fictional demo knowledge base:

* **retrieval hit rate**   — did the expected document appear in the top-k?
* **answer grounding**     — did the required fact appear in the generated answer?
* **refusal correctness**  — for out-of-scope questions, did the assistant refuse
  without calling the LLM?
* **source accuracy**      — were the cited sources the real retrieved chunks?

Usage::

    python -m evaluation.evaluate_rag                 # full report
    python -m evaluation.evaluate_rag --json          # machine readable
    python -m evaluation.evaluate_rag --threshold 0.6 # override the threshold
    python -m evaluation.evaluate_rag --seed          # index the demo documents first
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.database.session import init_db  # noqa: E402
from app.rag.metrics import rag_metrics  # noqa: E402
from app.rag.pipeline import pipeline  # noqa: E402
from app.rag.vector_store.qdrant_store import vector_store  # noqa: E402
from evaluation.dataset import EVAL_CASES, EvalCase  # noqa: E402


@dataclass
class CaseResult:
    case: EvalCase
    passed: bool
    score: float
    top_score: float
    sources: list[str]
    answer: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "category": self.case.category,
            "question": self.case.question,
            "in_domain": self.case.in_domain,
            "passed": self.passed,
            "score": round(self.score, 4),
            "top_score": round(self.top_score, 4),
            "sources": self.sources,
            "reason": self.reason,
            "answer": self.answer if len(self.answer) < 400 else self.answer[:397] + "...",
            **self.details,
        }


def _matches_document(filename: str, expected: str) -> bool:
    return expected.lower().replace(" ", "_") in filename.lower().replace(" ", "_")


async def evaluate(threshold: float | None = None) -> list[CaseResult]:
    results: list[CaseResult] = []

    for case in EVAL_CASES:
        if case.in_domain:
            chunks, retrieval = await pipeline.search_only(
                case.question, score_threshold=threshold
            )
            sources = [chunk.filename for chunk in chunks]
            top = retrieval.top_score if chunks else 0.0

            if not chunks:
                results.append(
                    CaseResult(
                        case=case,
                        passed=False,
                        score=0.0,
                        top_score=top,
                        sources=[],
                        answer="",
                        reason="no chunk passed the relevance threshold",
                    )
                )
                continue

            expected_hit = any(
                _matches_document(filename, expected)
                for filename in sources
                for expected in case.expected_documents
            )
            if not expected_hit:
                results.append(
                    CaseResult(
                        case=case,
                        passed=False,
                        score=0.0,
                        top_score=top,
                        sources=sources,
                        answer="",
                        reason=f"expected one of {case.expected_documents}, got {sources}",
                    )
                )
                continue

            result = await pipeline.query(case.question)
            answer = result.answer
            lowered = answer.lower()

            missing = [phrase for phrase in case.must_contain if phrase.lower() not in lowered]
            leaked = [phrase for phrase in case.must_not_contain if phrase.lower() in lowered]
            grounded = bool(result.sources)
            passed = grounded and not missing and not leaked

            reason = "ok"
            if not grounded:
                reason = "answer produced without sources"
            elif missing:
                reason = f"answer missing required facts: {missing}"
            elif leaked:
                reason = f"answer contained forbidden content: {leaked}"

            results.append(
                CaseResult(
                    case=case,
                    passed=passed,
                    score=retrieval.top_score,
                    top_score=top,
                    sources=[source["filename"] for source in result.sources],
                    answer=answer,
                    reason=reason,
                    details={"missing_facts": missing, "llm_called": result.context_used},
                )
            )
        else:
            chunks, retrieval = await pipeline.search_only(
                case.question, score_threshold=threshold
            )
            result = await pipeline.query(case.question, history=None)
            refused = result.no_context
            sources = [source["filename"] for source in result.sources]
            results.append(
                CaseResult(
                    case=case,
                    passed=refused,
                    score=retrieval.top_score if chunks else 0.0,
                    top_score=retrieval.top_score if chunks else 0.0,
                    sources=sources,
                    answer=result.answer,
                    reason="correctly refused" if refused else "answered an out-of-scope question",
                    details={"llm_called": result.context_used},
                )
            )

    return results


def summarise(results: list[CaseResult]) -> dict[str, Any]:
    in_domain = [r for r in results if r.case.in_domain]
    out_of_scope = [r for r in results if not r.case.in_domain]

    def rate(items: list[CaseResult]) -> float:
        return round(sum(1 for item in items if item.passed) / len(items), 4) if items else 0.0

    categories: dict[str, dict[str, Any]] = {}
    for result in results:
        entry = categories.setdefault(
            result.case.category, {"total": 0, "passed": 0, "avg_score": 0.0}
        )
        entry["total"] += 1
        entry["passed"] += int(result.passed)
        entry["avg_score"] += result.top_score
    for entry in categories.values():
        entry["avg_score"] = round(entry["avg_score"] / entry["total"], 4)
        entry["pass_rate"] = round(entry["passed"] / entry["total"], 4)

    scores = [r.top_score for r in in_domain]
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "pass_rate": rate(results),
        "retrieval_pass_rate": rate(in_domain),
        "refusal_pass_rate": rate(out_of_scope),
        "avg_in_domain_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "max_out_of_scope_score": round(
            max((r.top_score for r in out_of_scope), default=0.0), 4
        ),
        "categories": categories,
    }


def print_report(results: list[CaseResult], summary: dict[str, Any]) -> None:
    width = 92
    print("=" * width)
    print("HR NEXUS - RAG EVALUATION")
    print("=" * width)
    print(
        f"embedding={settings.EMBEDDING_MODEL} top_k={settings.TOP_K} "
        f"threshold={settings.SCORE_THRESHOLD} alpha={settings.HYBRID_ALPHA} "
        f"llm={settings.LLM_PROVIDER}"
    )
    print(f"collection={vector_store.collection} vectors={vector_store.count_vectors()}")
    print("-" * width)

    for result in results:
        flag = "PASS" if result.passed else "FAIL"
        scope = "in " if result.case.in_domain else "out"
        print(
            f"[{flag}] {scope} {result.case.id:<28} score={result.top_score:.3f}  "
            f"{result.case.question}"
        )
        if not result.passed:
            print(f"         reason: {result.reason}")
            if result.sources:
                print(f"         sources: {', '.join(result.sources)}")
            if result.answer:
                print(f"         answer : {result.answer[:220]}")
        else:
            print(f"         sources: {', '.join(result.sources) or '(refused, no sources)'}")

    print("-" * width)
    print("SUMMARY")
    for key in (
        "total",
        "passed",
        "pass_rate",
        "retrieval_pass_rate",
        "refusal_pass_rate",
        "avg_in_domain_score",
        "max_out_of_scope_score",
    ):
        print(f"  {key:<26} {summary[key]}")
    print("  per-category:")
    for category, entry in sorted(summary["categories"].items()):
        print(
            f"    {category:<14} {entry['passed']}/{entry['total']} "
            f"pass_rate={entry['pass_rate']} avg_score={entry['avg_score']}"
        )
    print(f"  pipeline metrics: {rag_metrics.snapshot()}")
    print("=" * width)


async def _seed() -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from seed_documents import seed  # type: ignore[import-not-found]

    paths = sorted(p for p in settings.DATA_DIR.iterdir() if p.suffix.lower() in (".pdf", ".md", ".txt"))
    await seed(paths, reindex=True)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    parser.add_argument("--threshold", type=float, default=None, help="override SCORE_THRESHOLD")
    parser.add_argument("--seed", action="store_true", help="re-index demo documents first")
    args = parser.parse_args()

    init_db()
    if args.seed:
        await _seed()

    results = await evaluate(threshold=args.threshold)
    summary = summarise(results)

    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "cases": [result.as_dict() for result in results],
                    "config": {
                        "embedding_model": settings.EMBEDDING_MODEL,
                        "top_k": settings.TOP_K,
                        "score_threshold": (
                            args.threshold if args.threshold is not None else settings.SCORE_THRESHOLD
                        ),
                        "hybrid_alpha": settings.HYBRID_ALPHA,
                        "llm_provider": settings.LLM_PROVIDER,
                        "collection": vector_store.collection,
                    },
                },
                indent=2,
            )
        )
    else:
        print_report(results, summary)

    vector_store.close()
    return 0 if summary["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
