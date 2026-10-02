# Deployment

Everything here runs with defaults — no API keys, no cloud account, no Docker
required. Each section moves one step further from your laptop.

---

## 1. Local development (no Docker)

Two terminals, from the repository root.

**Backend** (Python 3.11+; 3.12 recommended):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Optional: create a root .env from .env.example first.
uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to
<http://localhost:8000>, so the browser only ever talks to one origin. API docs
are at <http://localhost:8000/docs>.

The first start downloads the embedding model (`BAAI/bge-small-en-v1.5`, ~130 MB)
into the Hugging Face cache. Later starts reuse it.

### Load the sample corpus

```bash
python scripts/generate_sample_documents.py   # optional: regenerate the 7 fictional PDFs
python scripts/seed_documents.py              # index everything in data/documents
```

Both scripts accept `--help`. Every sample document is explicitly fictional and
prefixed `fictional_` so it can never be mistaken for a real company policy.

### Change the retrieval threshold

The threshold is the one number worth tuning. `backend/evaluation/evaluate_rag.py`
scores 26 answerable questions and 6 out-of-scope ones against the sample corpus
and prints the score distribution; pick a value in the gap and put it in `.env`:

```bash
cd backend
python -m evaluation.evaluate_rag
```

Re-run it after changing the corpus, the chunker or the embedding model — a
threshold that is correct for one corpus is not correct for another.

---

## 2. Docker Compose (single host)

```bash
cp .env.docker.example .env     # optional; every value has a working default
docker compose up --build
```

| Service | URL | Notes |
| --- | --- | --- |
| Web app | <http://localhost:8080> | nginx serves the bundle and proxies `/api` |
| API + docs | <http://localhost:8000/docs> | also reachable from the host for debugging |

What compose sets up for you:

- **Two volumes.** `api-data` holds the SQLite file, uploaded documents and the
  embedded Qdrant store, so `docker compose down` (without `-v`) keeps the corpus.
  `model-cache` keeps the embedding model so restarts do not re-download it.
  `QDRANT_PATH` and `DATA_DIR` are pinned to `/app/data/...` because the code
  defaults derive from the project root, which is `/` inside the image.
- **No credentials required.** `APP_ENV` defaults to `development` and the
  extractive provider needs no key, so the stack is useful immediately. (It
  deliberately does *not* default to `production`: that mode refuses the
  extractive provider and requires `API_AUTH_TOKEN`.)
- **Health gating.** The web container waits for `/api/health` to pass, so you
  never see nginx 502s while the model is still loading.

First build takes a few minutes (PyTorch wheels are large). Useful commands:

```bash
docker compose config                  # render the merged configuration
docker compose logs -f api             # watch the warm-up and the startup warnings
docker compose exec api python -m tests.smoke
docker compose down                    # stop, keep data
docker compose down -v                 # stop and delete the corpus
```

> **Not yet executed here.** These files were written on a machine without Docker.
> They were statically validated and two real defects were found by reading them
> (the vector-store path and the `APP_ENV` default, both now fixed — see
> `docs/PROJECT_STATUS.md` §2), but run `docker compose config` and one
> `up --build` before depending on them in CI.

---

## 3. Split origins (frontend and API on different hosts)

The bundle calls same-origin `/api` by default. For genuinely separate hosts:

**Frontend build:**

```bash
cd frontend
VITE_API_ORIGIN=https://api.example.com npm run build
```

`VITE_API_ORIGIN` is compiled into the bundle. It must be the API's public origin
with no trailing slash, and the value is public — never put a secret in it.

**Backend environment:**

```bash
CORS_ORIGINS=https://app.example.com
TRUST_PROXY_HEADERS=true
```

Static hosts need an SPA rewrite so deep links such as `/chat/<id>` resolve to
`index.html`. For Vercel:

```json
{ "rewrites": [{ "source": "/((?!api/).*)", "destination": "/index.html" }] }
```

For Netlify, `_redirects`:

```
/api/*  https://api.example.com/api/:splat  200
/*      /index.html                        200
```

Keep the server's streaming support intact: any proxy in front of the API needs
buffering disabled for `/api/chat/stream` (`proxy_buffering off` in
`frontend/nginx.conf`), otherwise answers arrive in one lump at the end.

---

## 4. Managed / PaaS backend

The API is a plain ASGI app, so it runs anywhere:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Checklist for a hosted deployment:

| Concern | What to do |
| --- | --- |
| Persistence | Mount a volume for `DATA_DIR`, or point `QDRANT_URL` at Qdrant Cloud. Ephemeral filesystems lose the corpus on every deploy. |
| Database | Set `DATABASE_URL=postgresql+psycopg://…`. The models are portable; nothing is SQLite-specific, and `psycopg[binary]` is already in `requirements.txt`. |
| Paths | Set `DATA_DIR` and `QDRANT_PATH` explicitly on a platform with an ephemeral filesystem, or point `QDRANT_URL` at Qdrant Cloud. Paths default to the project root, which is `/` inside a container image. |
| Proxy headers | `TRUST_PROXY_HEADERS=true` so the client IP and https scheme come from `X-Forwarded-*`. |
| CORS | Set `CORS_ORIGINS` to the exact frontend origin. |
| Secrets | `LLM_API_KEY`, `QDRANT_API_KEY`, `API_AUTH_TOKEN`, `DATABASE_URL` from the platform's secret store — never in the image. |
| Health | Point the platform's check at `/api/health/ready` (dependencies included) or `/api/health/live` (process only). |
| Workers | Keep one worker per volume. In-process rate limiting and the embedded Qdrant store assume a single writer. |
| Migrations | Startup adds missing columns automatically. Anything destructive needs a real migration run first. |

### Environment reference

Full list with comments: `.env.example`. The ones that matter most:

| Variable | Default | Effect |
| --- | --- | --- |
| `LLM_PROVIDER` | `extractive` | `extractive` quotes retrieved sentences; `openai` / `anthropic` / `gemini` generate |
| `LLM_API_KEY` | empty | Required by every provider except `extractive` |
| `SCORE_THRESHOLD` | `0.58` | Minimum hybrid score for a chunk to reach the prompt |
| `HYBRID_ALPHA` | `0.65` | Weight of cosine vs lexical coverage |
| `RETRIEVAL_CANDIDATES` | `30` | Candidates pulled before re-ranking |
| `QDRANT_URL` | `local` | `local` = embedded store; otherwise a Qdrant URL |
| `DATABASE_URL` | `sqlite:///./data/hr_nexus.db` | Point at PostgreSQL in production |
| `API_AUTH_TOKEN` | empty | When set, every write requires `Authorization: Bearer <token>` |
| `AUTH_REQUIRED` | unset | Force write protection on or off regardless of the token |
| `TRUST_PROXY_HEADERS` | `false` | Set `true` behind a reverse proxy |
| `RAG_DEBUG` | `false` | Returns the full retrieval trace in chat responses |

---

## 5. Production checklist

- [ ] `APP_ENV=production`, `DEBUG=false`, `RAG_DEBUG=false` (note: `production`
      refuses the `extractive` provider, so a real `LLM_PROVIDER` + `LLM_API_KEY`
      are required at the same time)
- [ ] `API_AUTH_TOKEN` set to a long random value, or write endpoints intentionally open
- [ ] `CORS_ORIGINS` lists only your real frontend origins
- [ ] `TRUST_PROXY_HEADERS=true` if behind a proxy; streaming not buffered
- [ ] Persistent storage for `DATA_DIR` and the Qdrant collection (or `QDRANT_URL` to a managed cluster)
- [ ] PostgreSQL instead of SQLite if more than one instance
- [ ] A real `LLM_PROVIDER` if you want generated answers, and the startup warning about `extractive` resolved
- [ ] `/api/health/ready` wired to the platform's health check
- [ ] `npm run build` output served with compression and immutable caching for hashed assets
- [ ] `python -m tests.smoke` passing against the deployed URL
