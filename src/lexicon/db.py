"""SQLite database access layer for the aenigmata lexical engine.

Usage:
    python -m src.lexicon.db --init            # create schema (idempotent)
    python -m src.lexicon.db --init --reset    # drop all tables and recreate
    python -m src.lexicon.db --init --db PATH  # use a non-default database file
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

_DEFAULT_DB: Path = Path(__file__).parent.parent.parent / "data" / "lexicon.db"
_SCHEMA: Path = Path(__file__).parent / "schema.sql"

# Drop order respects foreign-key dependencies (dependents before parents).
_DROP_ORDER: list[str] = [
    "token_lemma_links",
    "drift_flags",
    "cross_references",
    "semantic_fields",
    "attestations",
    "definitions",
    "sources",
    "lemmas",
]


def get_connection(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    """Return a SQLite connection with row factory and foreign-key enforcement.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open sqlite3.Connection.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = _DEFAULT_DB, *, reset: bool = False) -> None:
    """Initialize the database schema from schema.sql.

    The schema uses CREATE TABLE IF NOT EXISTS, so calling this on an already-
    initialized database is a safe no-op unless reset=True.

    Args:
        db_path: Path to the SQLite database file (created if absent).
        reset: Drop all tables before applying the schema.  Use to wipe and
               rebuild the database from scratch.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA.read_text(encoding="utf-8")

    with get_connection(db_path) as conn:
        if reset:
            for table in _DROP_ORDER:
                conn.execute(f"DROP TABLE IF EXISTS {table}")  # noqa: S608 — hardcoded list
        conn.executescript(schema)

    print(f"Database initialized: {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manage the aenigmata lexical database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--init", action="store_true", help="Initialize the schema.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables before initializing (destructive).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB,
        metavar="PATH",
        help=f"Database file path (default: {_DEFAULT_DB})",
    )
    args = parser.parse_args()

    if args.init:
        init_db(args.db, reset=args.reset)
    else:
        parser.print_help()
