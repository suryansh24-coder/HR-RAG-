# Implementation Plan

**Companion to:** `docs/PROJECT_STATUS.md`
**Principle:** nothing ships until it is verified by a command that can fail.

---

## Phase 1 — Backend correctness ✅ COMPLETE

**Why first:** the existing backend looked complete but three of its core paths
were broken (retrieval 500'd, the offline provider crashed, document deletion
destroyed neighbouring documents). A beautiful UI over a broken API is worthless.

- [x] Repair Qdrant 1.19 API, `session_scope`, nested `asyncio.run`
- [x] Fix cross-document data loss in document deletion
- [x] Repair `/api/meta` response model and `chunks_pending` mislabel
- [x] Rebuild retrieval as hybrid semantic + lexical scoring
- [x] Calibrate `SCORE_THRESHOLD` against a labelled evaluation set
- [x] Rebuild the extractive provider (window scoring, heading handling, quantity
      questions) so it stops dropping the sentence that holds the answer
- [x] Verification harness: `evaluation/` (32 cases) + `tests/smoke.py` (50 assertions)

**Exit criteria — met:** 41 unit tests, 32/32 evaluation, 50/50 smoke assertions.

---

## Phase 2 — Frontend ✅ COMPLETE

**Why second:** the backend was correct but unusable — the only interface was
Swagger.

### 2.1 Scaffold

- [x] Vite 5 + React 18 + TypeScript 5.6, strict mode
- [x] Tailwind CSS 3.4 with a design-token theme (no ad-hoc colour values)
- [x] React Router 6 for `/`, `/chat/:conversationId`, `/documents`, `/dashboard`
- [x] `lucide-react` icons, `react-markdown` + `remark-gfm` for answer text
- [x] Vitest + Testing Library, wired into `npm test`

### 2.2 API layer

- [x] Typed client hand-written against the real Pydantic schemas — **no `any`**,
      and no field name the API does not return (the smoke test exists precisely
      because that assumption was wrong for `chunks_pending`, `/api/rag/search`
      and the SSE event shape)
- [x] `api.chat()` buffered and `streamChat()` SSE with a clean
      `start → retrieving → sources → generating → complete | error` state machine;
      a truncated stream raises `stream_truncated` rather than returning a partial
      answer
- [x] Abort in-flight streams on navigation; surface `error` events as UI state,
      not console noise
- [x] Management token held in a module variable for the tab's lifetime, never in
      `localStorage`
- [x] Optional `VITE_API_ORIGIN` for split-origin deployments, same-origin by
      default

### 2.3 Screens

- [x] **Chat** — message list, streaming answer, collapsible source citations with
      filename, page, score and snippet, "open the source file", suggested
      follow-ups, stop button, copy answer
- [x] **Documents** — drag-and-drop upload with client-side size/type checks and
      real progress, live `pending → processing → ready | failed` polling, chunk
      counts, chunk preview, reindex, delete with confirmation
- [x] **Dashboard** — real numbers from `/api/rag/stats` and `/api/rag/queries`
      only. No invented metrics, no placeholder charts. Hero with live knowledge-base
      summary, system-status pills and quick questions that hand off to chat
      (`/chat?q=…`, answered by the same pipeline)
- [x] **Provider banner** — when `llm_provider === "extractive"`, states plainly
      that answers are quoted extracts rather than generated prose
- [x] **History** — conversation drawer with reopen and delete; the URL follows the
      active thread so a reload returns to it

### 2.5 Visual design

- [x] Frosted glass surfaces (`.glass`, `.glass-card`, `.glass-inset`) over an
      ambient aurora backdrop, driven by the same tokens as the rest of the design
      system so both themes keep their contrast
- [x] No layout dependency on `backdrop-filter`: it degrades to the translucent
      fill, and `prefers-reduced-motion` still wins over the transitions

### 2.4 Quality gates

- [x] `npm run build` clean under `tsc --noEmit`
- [x] `npm test` green (40 tests)
- [x] Keyboard accessible, focus-visible, respects `prefers-reduced-motion`
- [x] Empty, loading, error and offline states for every async surface
- [x] Works at 360px, 768px and 1440px
- [x] Light and dark themes from one set of tokens, with a toggle
- [x] Management-token gate replaces write controls on a protected deployment
- [x] Frontend bugs found and fixed while testing: `/chat` dropped the query
      string (so a dashboard hand-off lost the question), and navigating to
      `/chat/<id>` mid-stream remounted the chat screen and discarded the answer
      being received. Both are covered by tests.

**Exit criteria — met:** a reviewer can upload a policy, ask a question, read the
cited answer, watch the assistant refuse an unanswerable question, reopen the
thread later and delete a document — entirely through the UI, on a real backend.

---

## Phase 3 — Packaging & deployment 🟡 FILES WRITTEN, NOT EXECUTED

- [x] `backend/Dockerfile` (multi-stage, non-root, healthcheck)
- [x] `frontend/Dockerfile` (build + nginx) and `frontend/nginx.conf` with the
      `/api` proxy, `proxy_buffering off` for SSE and an SPA fallback
- [x] `docker-compose.yml`: web + api, healthchecks, two volumes (corpus, model
      cache), `.env` wiring
- [x] `.dockerignore` for both contexts
- [x] `docs/DEPLOYMENT.md`, including the split-origin and PaaS notes
- [x] `README.md` replacing the placeholder
- [x] Defects found by static review and fixed: the vector store wrote to
      `/data/qdrant` inside the image (outside the mounted volume, unwritable by
      the `nexus` user), and the stack defaulted to `APP_ENV=production` with the
      `extractive` provider, which production refuses — a chat endpoint that 503s
      in a container reporting itself healthy. `psycopg[binary]` added so the
      documented PostgreSQL switch actually connects.
- [ ] **Still open:** Docker is not installed on this machine, so the images have
      never been built. Run `docker compose config` and one `docker compose up
      --build` on a machine that has Docker, and fix whatever it reports. Do not
      claim the stack runs in Docker until that is done.

---

## Phase 4 — Production hardening ⬜ NEXT

- [ ] Versioned migrations (Alembic) for anything destructive; the additive
      `schema_sync` covers column additions only
- [ ] Verify the PostgreSQL path against a real instance
- [ ] Per-user auth — the shared bearer token is not acceptable for real HR data
- [ ] Shared (Redis) rate limiting, since the current limiter is per process
- [ ] `QueryLog` retention policy and a purge job (HR questions are sensitive)
- [ ] CI running: unit tests → evaluation → smoke → frontend build

---

## Phase 5 — Retrieval quality ⬜

Deliberately last: the current pipeline is *correct and honest*, and every further
improvement must be justified by a movement in the evaluation numbers.

- [ ] Grow the evaluation set to 100+ cases, including adversarial paraphrases
- [ ] Chunking experiment: 800 → 500 chars, measured, not assumed
- [ ] Compare `bge-small` against `bge-base` and a Qdrant server deployment
- [ ] Re-calibrate `SCORE_THRESHOLD` after any of the above, and record the
      before/after numbers in `PROJECT_STATUS.md`
- [ ] Optional: cross-encoder reranking for the top 30 candidates

---

## Explicit non-goals

- **No mock data in the UI.** Every number comes from the API; the demo corpus is
  clearly labelled fictional.
- **No "AI" theatre.** No fake confidence bars, no invented activity feeds, no
  decorative loading shimmer that implies work that is not happening.
- **No claiming completion without a passing command.** Phase 3–5 items stay
  unchecked until verified.
