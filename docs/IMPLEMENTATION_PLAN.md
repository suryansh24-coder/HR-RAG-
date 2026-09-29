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
- [x] Verification harness: `evaluation/` (32 cases) + `tests/smoke.py` (47 assertions)

**Exit criteria — met:** 36 unit tests, 32/32 evaluation, 47/47 smoke assertions.

---

## Phase 2 — Frontend ⬜ NEXT

**Why now:** it is the largest remaining gap and the one the product is judged on.
`frontend/` is an empty directory; the only UI that exists is FastAPI's Swagger
page, which no user should have to see.

### 2.1 Scaffold

- [ ] Vite 5 + React 18 + TypeScript 5.6, strict mode
- [ ] Tailwind CSS 3.4 with a design-token theme (no ad-hoc colour values)
- [ ] React Router 6 for `/`, `/chat/:conversationId?`, `/documents`, `/about`
- [ ] `lucide-react` icons, `framer-motion` for transitions, `react-markdown` +
      `remark-gfm` for rendering answer text
- [ ] Vitest + Testing Library, wired into `npm test`

### 2.2 API layer

- [ ] Typed client generated from `/openapi.json` — **no hand-written `any`**, and
      no frontend field name that the API does not actually return (the smoke
      test exists precisely because that assumption was wrong for `chunks_pending`,
      `/api/rag/search` and the SSE event shape)
- [ ] `fetchChat()` buffered and `streamChat()` SSE with a clean
      `start → retrieving → sources → generating → complete | error` state machine
- [ ] Abort in-flight streams on navigation; surface `error` events as UI state,
      not console noise
- [ ] Types for the management token, kept in memory only (never `localStorage`)

### 2.3 Screens

- [ ] **Chat** — message list, streaming answer, collapsible source citations
      showing filename, page, score and snippet, suggested follow-ups, stop
      button, copy-answer
- [ ] **Documents** — drag-and-drop upload with client-side size/type checks and
      real progress, live `pending → processing → ready | failed` polling, chunk
      counts, preview, re-index, delete with confirmation
- [ ] **Dashboard** — real numbers from `/api/rag/stats` only. No invented
      metrics, no placeholder charts.
- [ ] **Provider banner** — when `llm_provider === "extractive"`, state plainly
      that answers are quoted extracts, not generated prose

### 2.4 Quality gates

- [ ] `npm run build` clean under `tsc --noEmit`
- [ ] `npm test` green
- [ ] Keyboard accessible, focus-visible, respects `prefers-reduced-motion`
- [ ] Empty, loading, error and offline states for every async surface
- [ ] Works at 360px, 768px and 1440px

**Exit criteria:** a reviewer can sign in, upload a policy, ask a question, read
the cited answer, see the assistant refuse an unanswerable question, and delete a
document — entirely through the UI, on a real backend.

---

## Phase 3 — Packaging & deployment ⬜

- [ ] `Dockerfile` (backend) and `Dockerfile` (frontend, nginx + `/api` proxy)
- [ ] `docker-compose.yml`: app + postgres + qdrant, healthchecks, `.env` wiring
- [ ] **Blocked locally:** Docker is not installed on this machine, so compose
      must be validated by `docker compose config` on a machine that has it. Do
      not claim it runs until that is done.
- [ ] `README.md` replacing the 9-byte placeholder: quickstart, architecture,
      configuration table, retrieval tuning, troubleshooting

---

## Phase 4 — Production hardening ⬜

- [ ] Alembic migrations + `psycopg`; verify `create_all()` dev path still works
- [ ] Per-user auth (the shared bearer token is not acceptable for real HR data)
- [ ] Rate limiting on `/api/chat`, not just upload
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
- **No claiming completion without a passing command.** Phase 2–5 items stay
  unchecked until verified.
