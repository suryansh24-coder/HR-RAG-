# Testing

Four layers, each answering a different question. Run them in this order — the
fast ones first.

| Layer | Command | Scope | Time |
| --- | --- | --- | --- |
| Unit (backend) | `python -m pytest tests -q` | scoring, chunking, provider, schema sync | ~2 s |
| Evaluation | `python -m evaluation.evaluate_rag` | retrieval quality + refusal on 32 questions | ~1 min |
| Smoke (API) | `python -m tests.smoke` | 50 assertions against a real server | ~1 min |
| Unit (frontend) | `npm run typecheck && npm test` | 40 tests + types | ~20 s |

From the repository root, the backend commands run in `backend/` and the frontend
ones in `frontend/`.

---

## 1. Backend unit tests

```bash
cd backend
python -m pytest tests -q
```

- `tests/test_scorer.py` — hybrid scoring and the lexical-coverage gate: a chunk
  that merely shares a stop word with the question must not pass, and a chunk with
  real term overlap must.
- `tests/test_text_pipeline.py` — text cleaning, chunk size/overlap invariants, and
  the extractive provider (grounded, deterministic, and never inventing a number
  that is not in the context).
- `tests/test_schema_sync.py` — the additive column migration: it adds the columns
  an older database lacks, keeps existing rows readable, and is a no-op on a fresh
  schema.

## 2. Retrieval evaluation

```bash
cd backend
python -m evaluation.evaluate_rag
```

32 cases against the sample corpus: 26 answerable questions across leave,
resignation, benefits, attendance, WFH, conduct and onboarding, plus 6
out-of-scope questions that must be refused. Prints per-category pass rates, the
score distribution, the chosen threshold's behaviour, and pipeline latency.

This is the suite to run after changing the corpus, the chunker, the embedding
model, `SCORE_THRESHOLD` or `HYBRID_ALPHA`. It uses the extractive provider, so it
needs no API key and is deterministic.

## 3. API smoke test

```bash
cd backend
python -m tests.smoke
```

Starts its own server on a temporary database and vector collection, then asserts
50 things end to end: health and readiness, meta and chat config, upload →
background indexing → `ready`, a grounded answer with real sources, an
out-of-scope refusal, retrieval search, stats reflecting the new document,
streaming (stages, sources and grounded follow-ups), conversation persistence,
reindex, delete, and that the vectors are gone afterwards.

It cleans up after itself, including the document it uploads.

## 4. Frontend

```bash
cd frontend
npm run typecheck     # tsc --noEmit, strict
npm test              # vitest
npm run build         # tsc + production bundle
```

- `src/test/api-contract.test.ts` — the typed client's URLs, methods and error
  mapping against mocked responses.
- `src/test/client.test.ts` — SSE parsing, including a truncated stream, which must
  raise a `stream_truncated` error instead of silently returning a partial answer.
- `src/test/app.test.tsx` — real component behaviour: the shell's connection state
  and theme toggle, chat submit rules, conversation threading across turns, the
  history drawer, document status rendering, and the management-token gate.

The test run prints React Router v7 future-flag warnings. They are informational.

---

## Manual verification worth doing once

The automated suites cannot judge whether an answer is *good*, only whether it is
grounded. With `docker compose up --build` and the sample corpus indexed:

1. Ask a question the corpus answers (`How many days of annual leave do I get?`) —
   check the cited filename and page match the document you open.
2. Ask something the corpus does not cover (`What is our equity vesting schedule?`)
   — check the refusal, with no sources attached.
3. Upload a document and watch `pending → indexing → ready`, then ask about it
   before reloading the page.
4. Delete it, reload, and confirm it is gone from both the list and the vector
   count on the dashboard.
5. Switch the theme, resize to mobile width, and confirm both remain usable.
6. With `API_AUTH_TOKEN` set, reload the app: reading works, writing asks for the
   token.
