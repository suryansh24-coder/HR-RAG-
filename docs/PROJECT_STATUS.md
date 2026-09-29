# Project Status

**Last updated:** 2026-09-29
**Repository state:** single commit (`b0f0cac Initial commit`); all current work is uncommitted and unpushed.

> This document is written from verified test output, not from intent. Every
> "verified" claim below was produced by running the command shown next to it.

---

## 1. Summary

| Area | State | Evidence |
| --- | --- | --- |
| RAG ingestion pipeline | **Complete, verified** | 7 demo documents -> 37 chunks indexed |
| Retrieval quality | **Complete, verified** | 32/32 evaluation cases pass |
| Grounded answer generation | **Complete, verified** | `extractive` + 3 hosted providers |
| Refusal on unknown questions | **Complete, verified** | 6/6 out-of-scope questions refused |
| HTTP API | **Complete, verified** | 47/47 smoke assertions, 24 documented endpoints |
| Unit tests (pure logic) | **Complete, verified** | 36/36 pass |
| Frontend | **Not started** | `frontend/` is empty |
| Docker / compose | **Not started** | Docker not installed on this machine |
| PostgreSQL migrations | **Not started** | SQLite only, no Alembic |

---

## 2. What was broken on arrival, and what fixed it

These were real defects found by inspection and runtime probing, not hypotheticals.

| # | Defect | Impact | Fix |
| --- | --- | --- | --- |
| 1 | `QdrantClient.search` used, removed in `qdrant-client` 1.19 | **Every retrieval request 500'd** | Switched to `query_points` in `qdrant_store.py` |
| 2 | `str * list` in `extractive.py` | Offline provider crashed on first use | Rewrote provider; 11 unit tests cover it |
| 3 | `session_scope` missing `@contextmanager` | DB session leaked on every request | Decorator restored |
| 4 | Nested `asyncio.run` in `documents.py` | Background indexing failed with `RuntimeError` | Routes now call the sync service entry point |
| 5 | `shutil.rmtree(shard)` on delete | **Deleting one document wiped every document sharing its 2-char id prefix** | Delete the file; prune the shard only when empty |
| 6 | `/api/meta` typed `MessageResponse` | `version` and `features` were stripped from the response | Added `MetaResponse` |
| 7 | `chunks_pending` reported stored chunks | Dashboard mislabelled counts | Renamed to `chunks_indexed` |
| 8 | 4-char prefix stemmer | `overtime`→`over`, `competitor`→`company` (matched "company" in unrelated docs) | Suffix-stripping stemmer + guarded fuzzy prefix match |
| 9 | `chunk_text("")` returned `[""]` | Empty chunk could be embedded and win a search | `split_paragraphs` returns `[]` |
| 10 | Mojibake in cleaning regex + chunker docstring | Page-footer regex broken; docs unreadable | Repaired |
| 11 | Deprecated `get_sentence_embedding_dimension()` | Deprecation warning on every startup | Falls back to `get_embedding_dimension()` |

---

## 3. Why retrieval was rebuilt (the important part)

Pure cosine similarity could not refuse. Measured against the demo corpus:

```
"What is the company's stock trading policy?"  ->  0.625 cosine against an HR document
```

An embedding model always returns *something* nearby, so a cosine threshold is
either loose enough to answer unanswerable questions or tight enough to reject
legitimate ones. The fix was **hybrid scoring** in `app/rag/retrieval/scorer.py`:

1. **Hybrid score** = `0.65 x cosine + 0.35 x lexical coverage`, where coverage is
   the share of the question's *distinctive* terms (question words and HR
   boilerplate removed) that literally appear in the chunk.
2. **No-signal gate** — a chunk sharing *zero* distinctive terms with a specific
   question is rejected outright, whatever the cosine says.
3. **Per-document cap** — no single document can flood the context.
4. **Over-fetching** — 30 candidates are pulled and re-ranked, not 4. Pure cosine
   ranks the wrong chunk first for questions whose answer sentence shares no
   wording with the question.

Two approaches were tried and **rejected on evidence**, which is why they are not
in the code:

- **Anchor-term penalty** (require the question's longest terms to appear). It
  broke a correct case — it demoted the work-from-home chunk for *"How many office
  days per week do hybrid employees need to attend?"* because "attend" was absent —
  and did not fix the out-of-scope case it was built for.
- **Corpus-coverage gate** (refuse when the question's terms are absent from the
  whole corpus). Measured across all 32 cases, it does **not** separate: an
  out-of-scope "CEO's home address" scores 0.67, *above* in-domain questions that
  score 0.50. A gate that cannot separate is worse than no gate. The metric is
  still computed and traced, because it is the right thing to watch as the corpus
  grows.

### Calibrated threshold

`SCORE_THRESHOLD = 0.58` sits in the middle of the widest gap between the two
classes, measured over 26 answerable and 6 unanswerable questions:

```
lowest in-domain      0.6076   (attendance_overtime)
highest out-of-scope  0.5562   (oos_ceo_address)
```

**This calibration is only as good as the corpus it was measured on.** Re-run
`python -m evaluation.evaluate_rag` after changing the corpus, the chunker or the
embedding model.

---

## 4. Verification

Reproduce everything below from `backend/`:

```bash
python -m pytest tests/test_scorer.py tests/test_text_pipeline.py -q   # 36 unit tests
python -m evaluation.evaluate_rag                                     # 32/32 cases
python -m tests.smoke                                                 # 47/47 assertions
```

Latest results:

```
unit tests     36 passed
evaluation     32/32  (retrieval 26/26, refusal 6/6, avg in-domain score 0.77)
smoke          47 passed, 0 failed
```

`tests/smoke.py` drives the real stack end to end against a temporary SQLite
database and its own Qdrant collection: health, meta, upload -> background
indexing -> `ready`, retrieval, buffered chat, SSE streaming, refusal,
conversations, stats, re-index, delete + vector cleanup.

---

## 5. Known limitations

These are real and are **not** currently mitigated:

1. **The evaluation set is small.** 32 questions over 37 chunks. The refusal
   behaviour generalises only as well as that sample does.
2. **The demo corpus is tiny.** 7 documents, 37 chunks. Retrieval quality at
   10k+ chunks has not been measured here, and the corpus term index built by
   `QdrantVectorStore.corpus_terms()` scans every payload — it is cached and
   invalidated by vector count, but it is not appropriate at large scale.
3. **No PostgreSQL migrations.** SQLite only. `create_all()` is used instead of
   Alembic, so schema changes are not versioned.
4. **The `extractive` provider is not a language model.** It quotes retrieved
   sentences. It cannot synthesise, summarise or reason across documents. This is
   honest and deterministic, and it is why it is refused when
   `APP_ENV=production`; the UI should label it as such.
5. **Docker is unverified.** No Docker on this machine, so compose files can be
   written but not run.
6. **No rate limiting beyond the upload endpoint**, and the management token is a
   single shared bearer secret rather than per-user auth.

---

## 6. Running it today

```bash
# Backend
pip install -r backend/requirements.txt
python scripts/generate_sample_documents.py     # writes 7 fictional HR policies
python scripts/seed_documents.py                # indexes them into local Qdrant
uvicorn app.main:app --reload --app-dir backend

# Interactive docs
open http://localhost:8000/docs
```

Frontend: **not available yet** — see `docs/IMPLEMENTATION_PLAN.md`.
