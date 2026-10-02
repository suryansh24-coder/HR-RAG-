# Project Status

**Last updated:** 2026-10-02
**Repository state:** 5 commits (`dc2b660` latest); the work described in §2 and
the frontend/deployment completion below is uncommitted (58 changed/untracked
paths in the working tree).

> Written from verified command output, not intent. Every "verified" claim names
> the command that produced it.

---

## 1. Summary

| Area | State | Evidence |
| --- | --- | --- |
| RAG ingestion pipeline | **Complete, verified** | 7 documents → 37 chunks indexed in the live corpus |
| Retrieval quality | **Complete, verified** | 32/32 evaluation cases pass |
| Refusal on unknown questions | **Complete, verified** | 6/6 out-of-scope questions refused, live-tested |
| Answer generation | **Complete, verified** | `extractive` live-tested; 3 hosted providers implemented |
| HTTP API | **Complete, verified** | 50/50 smoke assertions; 27 endpoints under `/api` |
| Live end-to-end | **Complete, verified** | upload → index → answer → delete against a running server |
| Frontend | **Complete, verified** | 40 tests, strict typecheck, production build |
| Frontend ↔ backend contract | **Complete, verified** | stream now carries grounded follow-ups; 3 new UI tests |
| Visual design | **Complete, verified** | frosted glass surfaces over an ambient aurora, both themes, reduced-motion respected |
| Light/dark themes | **Complete, verified** | token swap on `<html data-theme>`, covered by a test |
| Conversation history | **Complete, verified** | drawer, `/chat/:id` deep links and `?conversation=` mid-stream ids, covered by tests |
| Write protection UX | **Complete, verified** | token gate replaces write controls, covered by a test |
| Docker / compose | **Files provided, not executed** | Docker is not installed on this machine; statically validated only |
| PostgreSQL | **Supported, not exercised** | driver now in `requirements.txt`; only SQLite has been run |
| Schema migrations | **Additive only** | `app/database/schema_sync.py`; no versioned migrations |

---

## 2. Defects found and fixed

Real defects, found by inspection and by running the thing — not hypotheticals.

| # | Defect | Impact | Fix |
| --- | --- | --- | --- |
| 1 | `QdrantClient.search` removed in `qdrant-client` 1.19 | **Every retrieval request 500'd** | Switched to `query_points` in `qdrant_store.py` |
| 2 | `str * list` in `extractive.py` | Offline provider crashed on first use | Rewrote the provider; unit-tested |
| 3 | `session_scope` missing `@contextmanager` | DB session leaked on every request | Decorator restored |
| 4 | Nested `asyncio.run` in `documents.py` | Background indexing failed with `RuntimeError` | Routes call the sync service entry point |
| 5 | `shutil.rmtree(shard)` on delete | **Deleting one document wiped every document sharing its 2-char id prefix** | Delete the file; prune the shard only when empty |
| 6 | `/api/meta` typed `MessageResponse` | `version` and `features` stripped from the response | Added `MetaResponse` |
| 7 | `chunks_pending` reported stored chunks | Dashboard mislabelled counts | Renamed to `chunks_indexed` |
| 8 | 4-char prefix stemmer | `overtime`→`over`, `competitor`→`company` (matched "company" in unrelated docs) | Suffix-stripping stemmer + guarded fuzzy prefix match |
| 9 | `chunk_text("")` returned `[""]` | An empty chunk could be embedded and win a search | `split_paragraphs` returns `[]` |
| 10 | Mojibake in cleaning regex + chunker docstring | Page-footer regex broken; docs unreadable | Repaired |
| 11 | Deprecated `get_sentence_embedding_dimension()` | Deprecation warning on every startup | Falls back to `get_embedding_dimension()` |
| 12 | **Database schema drift**: `create_all()` never alters a table, so a database created before `messages.no_context` existed failed every chat with `no such column: messages.no_context` | **Chat and history were broken on any pre-existing database** | `app/database/schema_sync.py` adds missing columns at boot (additive only, idempotent, unit-tested) |
| 13 | `SCORE_THRESHOLD=0.25` documented in `.env.example` vs `0.58` in code | A copied `.env` silently overrode the calibrated threshold | `.env.example` now documents the calibrated value and why |
| 14 | Frontend ignored the streamed `conversation_id` | Every turn after the first started a new conversation and lost the thread | Id captured on the `start` event, reused, and pushed into the URL |
| 15 | `AuthGate` existed but was never rendered | A protected deployment showed upload controls that could only fail with 401 | Documents page renders the gate; verified by test |
| 16 | Token verification called `window.location.reload()` | Unlocked, then immediately re-locked the user out | Callback-driven re-render instead |
| 17 | Frontend was hard-coded to a single dark palette | Requested light theme was absent | CSS custom properties per theme + toggle |
| 18 | Shadowed duplicate `reindex_in_background`, dead `AuthenticationError`/`ForbiddenError`/`to_payload`/`build_messages` | Misleading API surface | Removed |
| 19 | Starlette's renamed `HTTP_422_UNPROCESSABLE_ENTITY` | Deprecation warning on every validation error | Inlined as `UNPROCESSABLE = 422` with a comment |
| 20 | `QDRANT_PATH` defaulted to `PROJECT_ROOT/data/qdrant`, which is `/data/qdrant` inside the image | Embedded Qdrant wrote outside the mounted `/app/data` volume and was unwritable by the unprivileged `nexus` user, so every rebuild lost the vectors | Pinned `QDRANT_PATH=/app/data/qdrant` in `backend/Dockerfile` and `docker-compose.yml` |
| 21 | `docker-compose.yml` defaulted `APP_ENV=production` while `LLM_PROVIDER` defaulted to `extractive`, which `provider_factory()` refuses in production | The documented "works with no configuration" stack came up healthy and then 503'd every chat | Compose (and `.env.docker.example`) now default to `development`; production is documented as requiring a hosted provider + token |
| 22 | `psycopg` was documented as being in `requirements.txt` but was not there | Switching `DATABASE_URL` to `postgresql+psycopg://` failed at the first connection | `psycopg[binary]` added to `requirements.txt`; the docstring now matches reality |
| 23 | The frontend navigated from `/` to `/chat/<id>` on the stream's `start` event | Changing the *path* re-keys the route element, remounting `ChatPage` mid-answer — the streamed answer was discarded and replaced by a history fetch that predates it | The id now travels in the query string (`?conversation=<id>`), so the route does not change; `streamedIdRef` skips exactly that one redundant refetch. Covered by a test |
| 24 | `/api/chat/suggestions` existed and was called by nothing; the SSE `complete` event carried no follow-ups | The UI's suggestion chips could never render | Follow-ups are derived from the sources just retrieved and added to the `complete` event; asserted by both the smoke suite and a UI test |
| 25 | `README.md` and four files under `docs/` were double-encoded UTF-8 (em dashes as `â€”`, box drawing as `â""`) | The primary documentation was partly unreadable | Repaired by re-encoding through cp1252 → UTF-8 and verified: 0 mojibake sequences remain in the repo |
| 26 | Dead code: `PROCESSED_DIR`, `json_error`, `safe_detail`, `drop_db`, `database_url_display`, `LLMResult`, `new_trace_id`, `pipeline.stats`, `all_document_ids`, `filenames_by_document`, `indexed_documents`, `average_top_score`, `build_no_context_prompt`, `PromptBundle.as_messages`, `page_metadata`, a duplicate `load_document`, an unused `asyncio` import and the unused `framer-motion` dependency | Surface area that implied capabilities the code did not have | Removed, with `data/processed/` and its `.gitignore` entries deleted |

---

## 3. Why retrieval is hybrid (the load-bearing decision)

Pure cosine similarity cannot refuse. Measured against the sample corpus:

```
"What is the company's stock trading policy?"  ->  0.625 cosine against an HR document
```

An embedding model always returns *something* nearby, so a cosine threshold is
either loose enough to answer unanswerable questions or tight enough to reject
legitimate ones. `app/rag/retrieval/scorer.py` therefore scores each candidate as:

1. **Hybrid score** = `HYBRID_ALPHA` (0.65) × cosine + 0.35 × lexical coverage,
   where coverage is the share of the question's *distinctive* terms that literally
   appear in the chunk.
2. **No-signal gate** — a chunk sharing *zero* distinctive terms with a specific
   question is rejected whatever the cosine says.
3. **Per-document cap** — no single document can flood the context.
4. **Over-fetching** — `RETRIEVAL_CANDIDATES` (30) are pulled and re-ranked, not
   `TOP_K` (4). Pure cosine ranks the wrong chunk first when the sentence holding
   the answer shares no wording with the question.

Two alternatives were tried and **rejected on evidence**, which is why they are not
in the code:

- **Anchor-term penalty** (require the question's longest terms to appear). It broke
  a correct case — it demoted the work-from-home chunk for *"How many office days
  per week do hybrid employees need to attend?"* because "attend" was absent — and
  did not fix the out-of-scope case it was built for.
- **Corpus-coverage gate** (refuse when the question's terms are absent from the
  whole corpus). Across all 32 cases it does **not** separate: an out-of-scope
  "CEO's home address" scores 0.67, *above* in-domain questions scoring 0.50. A
  gate that cannot separate is worse than no gate. The metric is still computed and
  traced, because it is the right thing to watch as the corpus grows.

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

Everything below was run on 2026-10-02.

```bash
cd backend
python -m pytest tests -q                        # 41 passed
python -m evaluation.evaluate_rag                # 32/32 cases
python -m tests.smoke                            # 50 passed, 0 failed

cd ../frontend
npm run typecheck                                # clean
npm test                                         # 40 passed (3 files)
npm run build                                    # built in ~17s
```

Also run: a repo-wide scan for real key material (OpenAI/Anthropic/Google/GitHub
key shapes and `BEGIN PRIVATE KEY` blocks) in tracked files — **0 hits**, and
`.env` is git-ignored while only `.env.example` / `.env.docker.example` are
tracked.

Live end-to-end against a real `uvicorn` server on the existing corpus:

```
HEALTH: ok 1.0.0
STATS:  docs 7/7, chunks 37, qdrant ok, points 37
CHAT1:  grounded=True, 4 sources, top score 0.8346 (fictional_leave_policy.pdf p1)
CHAT2:  follow-up reused the same conversation id, 1 source
REFUSAL: no_context=True, 0 sources  ("confidential equity vesting schedule")
SSE:    start → retrieving → sources → generating → complete, conversation_id returned
UPLOAD: live_test_travel_policy.md → pending → ready (1 chunk, 1 vector)
ANSWER: grounded=True, source=live_test_travel_policy.md
DELETE: document and its vector removed; corpus back to 7 documents / 37 chunks
```

`tests/smoke.py` covers the same ground against a temporary database and its own
Qdrant collection; the run above was done separately against the *real* data
directory, which is how defect 12 was found — the smoke test builds its schema
from the current models, so it could not have caught it.

---

## 5. Known limitations

Real, and not currently mitigated:

1. **The evaluation set is small.** 32 questions over 37 chunks. Refusal behaviour
   generalises only as well as that sample does.
2. **The sample corpus is tiny.** 7 documents, 37 chunks. Quality at 10k+ chunks is
   unmeasured here, and `QdrantVectorStore.corpus_terms()` scans every payload — it
   is cached and invalidated by vector count, which is not appropriate at scale.
3. **Docker assets are unexecuted.** Docker is not installed on the machine that
   built this. They were statically validated (`docker-compose.yml` parses, both
   services resolve, volumes mount) and defects 20 and 21 were found by reading
   them, but `docker compose config` and one `up --build` should still be run before
   relying on them.
4. **PostgreSQL is supported but unexercised.** `DATABASE_URL` accepts a
   `postgresql+psycopg://` URL, the driver is now in `requirements.txt` and the
   models are portable; no PostgreSQL instance was available to test against.
5. **No versioned migrations.** Startup adds missing columns only. Destructive
   changes need a real migration tool.
6. **The `extractive` provider is not a language model.** It quotes retrieved
   sentences; it cannot synthesise or reason across documents. Running it in
   production logs a warning and is reported as `features.extractive` so the UI
   labels the mode.
7. **Rate limiting is per process** (`RATE_LIMIT_PER_MINUTE`,
   `RATE_LIMIT_UPLOADS_PER_MINUTE`) and in memory, so multiple replicas each keep
   their own budget.
8. **The management token is one shared secret.** There are no user accounts,
   roles or audit trails; it protects writes for a trusted team, nothing more.
9. **No per-user data isolation.** Every conversation and document is global to the
   deployment.

---

## 6. Running it today

```bash
# One command, everything included (Docker required)
docker compose up --build            # http://localhost:8080

# Or without Docker — backend
pip install -r backend/requirements.txt
python scripts/generate_sample_documents.py     # 7 fictional HR policies
python scripts/seed_documents.py                # index them into local Qdrant
uvicorn app.main:app --reload --app-dir backend

# …and frontend
cd frontend && npm install && npm run dev       # http://localhost:5173
```

`docs/DEPLOYMENT.md` covers hosted deployments; `docs/TESTING.md` covers the test
layers; `docs/ARCHITECTURE.md` describes the design and its trade-offs.
