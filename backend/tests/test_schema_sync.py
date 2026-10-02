"""Unit tests for the additive schema synchronisation.

These cover the failure this module exists to prevent: a database created by an
earlier version of the app is missing a column the models now declare, and
``create_all`` silently leaves it that way.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.schema_sync import describe, sync_schema  # noqa: E402
from app.database.session import Base  # noqa: E402

# The shape of `messages` before `no_context` and `latency_ms` were added.
LEGACY_SCHEMA = """
CREATE TABLE conversations (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
CREATE TABLE messages (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    conversation_id VARCHAR(32) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    sources JSON,
    created_at DATETIME NOT NULL
);
INSERT INTO conversations VALUES ('c1', 'Legacy thread', '2026-01-01', '2026-01-01');
INSERT INTO messages VALUES ('m1', 'c1', 'assistant', 'A legacy answer', NULL, '2026-01-01');
"""


@pytest.fixture()
def legacy_engine(tmp_path):
    """An engine over a database that predates the current models."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        for statement in LEGACY_SCHEMA.strip().split(";"):
            if statement.strip():
                connection.execute(text(statement))
    yield engine
    engine.dispose()


def columns_of(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


class TestSyncSchema:
    def test_adds_columns_the_models_gained(self, legacy_engine):
        applied = sync_schema(legacy_engine)

        assert any("no_context" in statement for statement in applied)
        assert {"no_context", "latency_ms"} <= columns_of(legacy_engine, "messages")

    def test_existing_rows_survive_and_get_a_usable_value(self, legacy_engine):
        sync_schema(legacy_engine)

        with legacy_engine.connect() as connection:
            row = connection.execute(
                text("SELECT content, no_context FROM messages WHERE id = 'm1'")
            ).one()

        assert row.content == "A legacy answer"
        # NOT NULL with a server default, so the old row is still readable as a
        # boolean rather than surfacing as None.
        assert row.no_context in (0, False)

    def test_is_idempotent(self, legacy_engine):
        first = sync_schema(legacy_engine)
        second = sync_schema(legacy_engine)

        assert first
        assert second == []

    def test_current_schema_needs_no_changes(self, tmp_path):
        from app.models import entities  # noqa: F401  (register the mappers)

        engine = create_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
        Base.metadata.create_all(bind=engine)
        try:
            assert sync_schema(engine) == []
            assert "missing" not in describe(engine)
        finally:
            engine.dispose()

    def test_describe_names_the_missing_columns(self, legacy_engine):
        summary = describe(legacy_engine)

        assert "messages" in summary
        assert "no_context" in summary
