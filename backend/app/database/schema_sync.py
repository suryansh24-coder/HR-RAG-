"""Additive schema synchronisation for existing databases.

`Base.metadata.create_all()` only ever **creates** missing tables. It never
alters a table that already exists, so a database created by an earlier version of
this project keeps its old shape and the first query against a newer column fails
with a driver error (for example ``no such column: messages.no_context``) instead
of a clear message.

Rather than pull in a migration tool for a four-table application, this module
applies the one migration that is safe to apply automatically: **adding a column
that the models declare and the database lacks.**

Deliberately out of scope, because doing them automatically is how data is lost:

* dropping or renaming a column or table,
* changing a column's type, nullability or default,
* backfilling values that a new column needs.

A deployment that needs any of those should run a real migration. Everything this
module does is idempotent, additive and logged, so running it on every boot is
safe: the second run finds nothing to do.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import Column

from app.database.session import Base, engine as default_engine

logger = logging.getLogger(__name__)

def _registered_metadata():
    """Import the models for their side effect and return the metadata.

    ``Base.metadata`` is empty until the mappers are registered, so anything that
    reads it must trigger that import itself rather than assume a caller did.
    """
    from app.models import entities  # noqa: F401  (register the mappers)

    return Base.metadata


def sync_schema(engine: Engine | None = None) -> list[str]:
    """Add any column declared by the models but missing from the database.

    Returns the statements that were applied, for logging and tests. Safe to call
    repeatedly and safe to call on an empty database, where ``create_all`` has
    already produced the current shape and this returns an empty list.
    """
    metadata = _registered_metadata()
    target = engine or default_engine
    applied: list[str] = []
    inspector = inspect(target)

    existing_tables = set(inspector.get_table_names())
    with target.begin() as connection:
        dialect = connection.dialect.name
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                # create_all made this table from the current models; nothing to
                # reconcile.
                continue

            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                statement = _add_column_statement(table.name, column, dialect)
                if statement is None:
                    logger.warning(
                        "Cannot add column %s.%s automatically: no safe default. "
                        "Create the column manually before starting the app.",
                        table.name,
                        column.name,
                    )
                    continue
                connection.execute(text(statement))
                applied.append(statement)
                logger.info("Schema sync: %s", statement)

    return applied


def _add_column_statement(table: str, column: Column, dialect: str) -> str | None:
    """Render ``ALTER TABLE ... ADD COLUMN`` for one column, or ``None``.

    ``None`` means the column cannot be added without risking existing rows and is
    the caller's cue to log loudly instead of guessing.
    """
    try:
        type_sql = column.type.compile(dialect=_dialect_for(dialect))
    except Exception:  # noqa: BLE001 - an uncompilable type is simply not migrated
        return None

    name = f'"{column.name}"'
    if column.nullable:
        return f'ALTER TABLE "{table}" ADD COLUMN {name} {type_sql}'

    # A NOT NULL column can only be added to a table that already has rows if the
    # database supplies a value for those rows. A scalar model default maps to a
    # SQL literal; a Python callable default (uuid, timestamp, ...) does not, and
    # is reported instead of being faked.
    literal = _literal_for(column, dialect)
    if literal is None:
        return None
    return f'ALTER TABLE "{table}" ADD COLUMN {name} {type_sql} NOT NULL DEFAULT {literal}'


def _dialect_for(name: str):
    """Return a dialect object for compiling types without a live connection."""
    from sqlalchemy.dialects import postgresql, sqlite

    return {"sqlite": sqlite.dialect(), "postgresql": postgresql.dialect()}.get(
        name, sqlite.dialect()
    )


def _literal_for(column: Column, dialect: str) -> str | None:
    default = column.default
    if default is None or not default.is_scalar:
        return None

    value = default.arg
    if value is None:
        return "NULL" if dialect != "postgresql" else "NULL"

    if isinstance(value, bool):
        if dialect == "postgresql":
            return "TRUE" if value else "FALSE"
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def describe(engine: Engine | None = None) -> str:
    """One-line summary of the current schema, for startup logs and debugging."""
    metadata = _registered_metadata()
    target = engine or default_engine
    inspector = inspect(target)
    existing_tables = set(inspector.get_table_names())
    lines: list[str] = []
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        missing = [column.name for column in table.columns if column.name not in present]
        suffix = f" (missing: {', '.join(missing)})" if missing else ""
        lines.append(f"{table.name}: {len(present)} columns{suffix}")
    return "; ".join(lines)
