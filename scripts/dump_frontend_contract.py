"""Print the response schemas for the endpoints the frontend consumes.

Used to keep `frontend/src/api/types.ts` honest: every type in it should be
justified by output from this script.
"""

import json
import sys

sys.path.insert(0, "backend")

from app.main import app  # noqa: E402

PATHS = [
    ("/api/documents", "get"),
    ("/api/documents/upload", "post"),
    ("/api/documents/{document_id}", "get"),
    ("/api/documents/{document_id}/reindex", "post"),
    ("/api/documents/limits/file", "get"),
    ("/api/conversations", "get"),
    ("/api/conversations/{conversation_id}", "get"),
    ("/api/conversations/{conversation_id}", "delete"),
    ("/api/chat", "post"),
    ("/api/chat/config", "get"),
    ("/api/rag/search", "post"),
    ("/api/rag/stats", "get"),
    ("/api/rag/queries", "get"),
    ("/api/auth/status", "get"),
]


def main() -> None:
    spec = app.openapi()
    schemas = spec["components"]["schemas"]

    for path, method in PATHS:
        op = spec["paths"][path][method]
        content = op.get("responses", {}).get("200", {}).get("content", {})
        ref = content.get("application/json", {}).get("schema", {})
        name = ref.get("$ref", "").split("/")[-1] or "(inline)"
        props = schemas.get(name, {}).get("properties", {})
        print(f"{method.upper():6} {path}\n       -> {name}")
        if props:
            print("       fields: " + ", ".join(sorted(props)))
        else:
            print("       fields: (inline/array) " + json.dumps(ref, default=str)[:160])
        print()

    print("=== SearchHit ===")
    print(json.dumps(schemas["SearchHit"]["properties"], indent=2, default=str))
    print("=== CollectionInfo ===")
    for candidate in schemas:
        if candidate.lower().startswith("collection"):
            print(candidate, json.dumps(schemas[candidate]["properties"], indent=2, default=str))
    print("=== Metrics/Config ===")
    for candidate in ("RagStatsResponse",):
        for key, value in schemas[candidate]["properties"].items():
            if key in ("metrics", "config", "collection"):
                print(candidate, key, "->", json.dumps(value, default=str)[:200])


if __name__ == "__main__":
    main()
