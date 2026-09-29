#!/usr/bin/env python
"""Index the fictional demo documents found in ``data/documents``.

Useful to populate the knowledge base without using the API, for local demos and
for the acceptance test.

Usage::

    python scripts/seed_documents.py              # index everything not indexed
    python scripts/seed_documents.py --reindex    # delete vectors and re-index
    python scripts/seed_documents.py --reset      # wipe documents + vectors first
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.database.session import init_db, session_scope  # noqa: E402
from app.models import Document  # noqa: E402
from app.rag.vector_store.qdrant_store import vector_store  # noqa: E402
from app.services.document_service import document_service  # noqa: E402

logger = get_logger("seed")

SUPPORTED = (".pdf", ".txt", ".md", ".markdown")


def discover(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and not path.name.startswith((".", "_"))
        and path.suffix.lower() in SUPPORTED
    )


def already_indexed(filename: str) -> Document | None:
    with session_scope() as db:
        return next(
            (d for d in document_service.list(db) if d.filename == filename), None
        )


async def seed(paths: list[Path], reindex: bool) -> int:
    count = 0
    for path in paths:
        existing = already_indexed(path.name)
        if existing and not reindex:
            print(f"  skip  {path.name} (already {existing.status}, {existing.chunk_count} chunks)")
            continue

        with session_scope() as db:
            if existing:
                document_id = existing.id
                await document_service.reindex(db, document_id)
            else:
                record = document_service.persist_upload(db, path.name, path.read_bytes())
                document_id = record.id
                print(f"  index {path.name}")
                await document_service.process(db, document_id)

        with session_scope() as db:
            record = db.get(Document, document_id)
            if record and record.status == "ready":
                print(
                    f"  ok    {record.filename}: {record.chunk_count} chunks, "
                    f"{record.page_count} pages, {record.processing_time_ms} ms"
                )
                count += 1
            else:
                print(f"  FAIL  {path.name}: {record.error_message if record else 'unknown'}")
    return count


async def reset() -> None:
    with session_scope() as db:
        for record in document_service.list(db):
            await document_service.delete(db, record.id)
            print(f"  removed {record.filename}")
    vector_store.delete_all()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reindex", action="store_true", help="re-index existing documents")
    parser.add_argument("--reset", action="store_true", help="delete all documents and vectors first")
    parser.add_argument("--dir", default=str(settings.DATA_DIR), help="directory to index")
    args = parser.parse_args()

    configure_logging()
    init_db()

    directory = Path(args.dir)
    paths = discover(directory)
    if not paths:
        print(f"No supported documents found in {directory}")
        print("Run: python scripts/generate_sample_documents.py")
        return 1

    print(f"Indexing {len(paths)} document(s) from {directory}")

    if args.reset:
        print("Resetting knowledge base")
        asyncio.run(reset())

    indexed = asyncio.run(seed(paths, reindex=args.reindex))

    print(f"\nVectors in collection: {vector_store.count_vectors()}")
    print(f"Documents indexed: {indexed}")
    return 0 if indexed or not args.reindex else 1


if __name__ == "__main__":
    sys.exit(main())
