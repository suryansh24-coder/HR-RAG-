"""End-to-end backend smoke test against the real stack.

Exercises the full request path with a real SQLite database and the real local
Qdrant collection: health, meta, document upload -> background indexing ->
retrieval, chat (buffered and streamed), refusal, sources, re-index, delete.

Usage::

    python -m tests.smoke            # uses a temporary DB and collection
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TMP = Path(tempfile.mkdtemp(prefix="hr-nexus-smoke-"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP / 'smoke.db'}",
    QDRANT_PATH=str(_TMP / "qdrant"),
    QDRANT_COLLECTION="smoke_chunks",
    LLM_PROVIDER="extractive",
    APP_ENV="development",
    API_AUTH_TOKEN="",
    AUTH_REQUIRED="false",
    LOG_LEVEL="warning",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.database.session import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.rag.vector_store.qdrant_store import vector_store  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name}  {detail}")


SAMPLE = b"""Northwind Digital - Test Travel Policy

Employees may claim up to 900 USD towards approved business travel expenses.
Claims must be submitted within 30 days of travel and require a receipt.
"""


def main() -> int:
    init_db()
    with TestClient(app) as client:
        print("\n--- health & meta ---")
        response = client.get("/api/health")
        check("GET /api/health -> 200", response.status_code == 200, response.text)
        health = response.json()
        check(
            "health reports database ok",
            health.get("components", {}).get("database", {}).get("status") == "ok",
            str(health),
        )
        check(
            "health reports vector store ok",
            health.get("components", {}).get("vector_store", {}).get("status") == "ok",
            str(health),
        )

        response = client.get("/api/health/live")
        check("GET /api/health/live -> 200", response.status_code == 200, response.text)

        response = client.get("/api/meta")
        check("GET /api/meta -> 200", response.status_code == 200, response.text)
        meta = response.json()
        check(
            "meta returns version + features (not stripped by response_model)",
            bool(meta.get("version")) and isinstance(meta.get("features"), dict),
            str(meta),
        )

        print("\n--- documents ---")
        response = client.get("/api/documents")
        check("GET /api/documents -> 200", response.status_code == 200, response.text)
        check("new database starts empty", response.json().get("total") == 0, response.text)

        response = client.post(
            "/api/documents/upload",
            files={"file": ("test_travel_policy.md", io.BytesIO(SAMPLE), "text/markdown")},
        )
        check("POST /api/documents/upload -> 201", response.status_code == 201, response.text)
        upload = response.json()
        document = upload.get("document") or {}
        document_id = document.get("id") or upload.get("document_id")
        check("upload returns a document id", bool(document_id), response.text)
        check("upload starts as pending", document.get("status") == "pending", response.text)

        status, detail = None, None
        for _ in range(60):
            response = client.get(f"/api/documents/{document_id}")
            if response.status_code != 200:
                check("GET /api/documents/{id} -> 200", False, response.text)
                break
            detail = response.json()
            status = detail.get("status")
            if status in ("ready", "failed"):
                break
            import time

            time.sleep(0.5)
        check(
            "background indexing reaches 'ready' (no nested-event-loop error)",
            status == "ready",
            f"status={status} error={(detail or {}).get('error_message')}",
        )
        check("indexed document reports chunks", bool((detail or {}).get("chunk_count")), str(detail))

        response = client.get("/api/documents")
        check("GET /api/documents lists the document", response.json().get("total") == 1, response.text)

        print("\n--- retrieval & chat ---")
        response = client.post(
            "/api/rag/search", json={"question": "What is the business travel claim limit?"}
        )
        check("POST /api/rag/search -> 200", response.status_code == 200, response.text)
        search = response.json()
        check("retrieval finds the uploaded policy", len(search.get("hits") or []) >= 1, response.text)
        check(
            "retrieval returns a source filename",
            bool((search.get("hits") or [{}])[0].get("filename")),
            response.text,
        )
        check(
            "retrieval hit carries a real score above the threshold",
            (search.get("hits") or [{}])[0].get("score", 0) > 0.58,
            response.text,
        )

        response = client.post(
            "/api/chat",
            json={"question": "What is the business travel claim limit and how long do I have to submit it?"},
        )
        check("POST /api/chat -> 200", response.status_code == 200, response.text)
        chat = response.json()
        check("chat returns an answer", bool(chat.get("answer")), response.text)
        check(
            "chat answer quotes the real figure",
            "900" in chat.get("answer", ""),
            chat.get("answer", ""),
        )
        check("chat returns real sources", len(chat.get("sources") or []) >= 1, response.text)
        conversation_id = chat.get("conversation_id")
        check("chat returns a conversation_id", bool(conversation_id), response.text)
        check(
            "chat source has filename + page",
            all({"filename", "page", "chunk_id"} <= set(s) for s in chat.get("sources") or []),
            response.text,
        )
        latency = chat.get("total_latency_ms")
        check(
            "chat reports a measured latency without RAG_DEBUG",
            isinstance(latency, (int, float)) and latency > 0,
            f"total_latency_ms={latency!r}",
        )

        print("\n--- refusal ---")
        response = client.post(
            "/api/chat", json={"question": "What is the office cat's name?"}
        )
        check("out-of-scope chat -> 200", response.status_code == 200, response.text)
        refused = response.json()
        check("out-of-scope question is refused", bool(refused.get("no_context")), response.text)
        check("refusal returns no sources", not refused.get("sources"), response.text)
        check(
            "refusal still reports a latency",
            isinstance(refused.get("total_latency_ms"), (int, float)),
            response.text,
        )

        print("\n--- streaming ---")
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"question": "How long do I have to submit a travel claim?"},
        ) as stream:
            check("POST /api/chat/stream -> 200", stream.status_code == 200)
            check(
                "stream sets the SSE content type",
                "text/event-stream" in stream.headers.get("content-type", ""),
                stream.headers.get("content-type", ""),
            )
            events, name = [], None
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    name = line[7:].strip()
                elif line.startswith("data: "):
                    events.append((name, json.loads(line[6:])))
        stages = [name for name, _ in events]
        check("stream emits a 'complete' stage", "complete" in stages, str(stages))
        check("stream emits a 'sources' stage", "sources" in stages, str(stages))
        check(
            "stream walks the full pipeline in order",
            stages == ["start", "retrieving", "sources", "generating", "complete"],
            str(stages),
        )
        complete = next((data for name, data in events if name == "complete"), {})
        check(
            "streamed answer contains the real figure",
            "30 days" in str(complete.get("answer", "")),
            str(complete)[:300],
        )
        check(
            "streamed complete event carries sources",
            bool(complete.get("sources")),
            str(complete)[:300],
        )
        check(
            "streamed complete event carries grounded follow-ups",
            bool(complete.get("suggestions")),
            str(complete)[:300],
        )


        print("\n--- conversations ---")
        response = client.get("/api/conversations")
        check("GET /api/conversations -> 200", response.status_code == 200, response.text)
        response = client.get(f"/api/conversations/{conversation_id}")
        check(
            "GET /api/conversations/{id} returns the persisted turn",
            response.status_code == 200 and len(response.json().get("messages", [])) == 2,
            response.text,
        )
        response = client.patch(f"/api/conversations/{conversation_id}", json={"title": "Travel policy"})
        check("PATCH conversation title -> 200", response.status_code == 200, response.text)
        check("PATCH persists the new title", response.json().get("title") == "Travel policy", response.text)

        print("\n--- rag stats ---")
        response = client.get("/api/rag/stats")
        check("GET /api/rag/stats -> 200", response.status_code == 200, response.text)
        stats = response.json()
        check("stats report indexed documents", stats.get("documents_indexed", 0) >= 1, response.text)
        check("stats report query counts", stats.get("queries_total", 0) >= 1, response.text)
        response = client.get("/api/rag/config")
        check("GET /api/rag/config -> 200", response.status_code == 200, response.text)

        print("\n--- reindex & delete ---")
        response = client.post(f"/api/documents/{document_id}/reindex")
        check("POST reindex -> 200/202", response.status_code in (200, 202), response.text)
        import time

        for _ in range(60):
            response = client.get(f"/api/documents/{document_id}")
            if response.json().get("status") in ("ready", "failed"):
                break
            time.sleep(0.5)
        check("reindex returns to 'ready'", response.json().get("status") == "ready", response.text)

        response = client.delete(f"/api/documents/{document_id}")
        check("DELETE /api/documents/{id} -> 204", response.status_code == 204, response.text)
        response = client.get(f"/api/documents/{document_id}")
        check("deleted document is gone (404)", response.status_code == 404, response.text)
        check(
            "delete removed the vectors",
            vector_store.count_for_document(document_id) == 0,
            str(vector_store.count_for_document(document_id)),
        )
        stored = list(Path(os.environ["QDRANT_PATH"]).parent.glob("**/*")) if False else None

    vector_store.close()

    print("\n" + "=" * 70)
    print(f"smoke: {len(PASSED)} passed, {len(FAILED)} failed")
    for failure in FAILED:
        print(f"  FAILED: {failure}")
    print("=" * 70)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

