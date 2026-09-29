import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "backend")
from app.core.config import settings

url = settings.DATABASE_URL
print("DATABASE_URL:", url)

path = url.split("///")[-1]
db = Path(path)
print("resolved:", db, "exists:", db.exists(), "size:", db.stat().st_size if db.exists() else 0)

if db.exists():
    connection = sqlite3.connect(db)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print("tables:", [row[0] for row in rows])
    for table in ("documents", "chunks", "conversations", "messages", "query_logs"):
        if table in [row[0] for row in rows]:
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")
    connection.close()
