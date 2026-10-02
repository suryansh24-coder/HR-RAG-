"""Print the resolved application database and its row counts.

The first thing to check when the dashboard shows zeros or the API logs a
``no such column`` error, because a relative ``DATABASE_URL`` resolves against
the project root, not the directory you happened to start uvicorn from.

    python scripts/check_dev_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402

# Tables the application owns. `chunks` is not one of them: chunk text lives in
# Qdrant, and only the count is kept here.
TABLES = ("documents", "conversations", "messages", "query_logs")


def main() -> int:
    print("DATABASE_URL:", settings.DATABASE_URL)
    if not settings.DATABASE_URL.startswith("sqlite"):
        print("Not a SQLite database; nothing to inspect locally.")
        return 0

    path = Path(settings.DATABASE_URL.split("///")[-1])
    print("resolved:", path, "exists:", path.exists())
    if not path.exists():
        print("The database has not been created yet — start the API once.")
        return 0
    print("size:", f"{path.stat().st_size / 1024:.0f} KB")

    import sqlite3

    connection = sqlite3.connect(path)
    try:
        present = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        print("tables:", sorted(present))
        for table in TABLES:
            if table in present:
                count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {count} rows")

        # A column the models declare but the file lacks is the failure mode that
        # `app/database/schema_sync.py` exists to repair; report it rather than
        # leaving it to be discovered as a 500.
        import sys as _sys

        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from app.database.schema_sync import describe

        print("schema:", describe())
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
