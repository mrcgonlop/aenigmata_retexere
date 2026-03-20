"""Training database access layer.

Database lives at data/training/training.db, separate from the lexical DB.
Schema is defined in src/training/schema.sql.

Usage:
    python -m src.training.db --init
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.lexicon.db import get_connection

_DEFAULT_TRAINING_DB = Path("data/training/training.db")
_SCHEMA = Path(__file__).parent / "schema.sql"


def get_training_connection(db_path: Path = _DEFAULT_TRAINING_DB) -> sqlite3.Connection:
    """Return a connection to the training database, creating it if necessary.

    Args:
        db_path: Path to the SQLite file (created on first call).

    Returns:
        An open sqlite3.Connection with row_factory and foreign keys enabled.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------

def insert_sample(
    conn: sqlite3.Connection,
    *,
    manuscript: str,
    folio: str,
    hand_id: str,
    line_image_path: str,
    source_line_bbox: list[int] | None,
    column_index: int | None,
    ocr_guess: str | None,
) -> int:
    """Insert a new training sample. Silently ignores duplicate image paths.

    Returns:
        The new row id, or 0 if the row already existed (UNIQUE conflict).
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO training_samples
            (manuscript, folio, hand_id, line_image_path, source_line_bbox,
             column_index, ocr_guess, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            manuscript,
            folio,
            hand_id,
            line_image_path,
            json.dumps(source_line_bbox) if source_line_bbox else None,
            column_index,
            ocr_guess,
        ),
    )
    conn.commit()
    return cur.lastrowid or 0


def save_label(conn: sqlite3.Connection, sample_id: int, ground_truth: str) -> None:
    """Confirm a transcription as ground truth."""
    conn.execute(
        """
        UPDATE training_samples
        SET ground_truth = ?, status = 'confirmed', labeled_at = ?
        WHERE id = ?
        """,
        (ground_truth, datetime.now(timezone.utc).isoformat(), sample_id),
    )
    conn.commit()


def skip_sample(conn: sqlite3.Connection, sample_id: int) -> None:
    """Mark a sample as skipped (unusable or ambiguous)."""
    conn.execute(
        "UPDATE training_samples SET status = 'skipped', labeled_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), sample_id),
    )
    conn.commit()


def get_sample(conn: sqlite3.Connection, sample_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM training_samples WHERE id = ?", (sample_id,)
    ).fetchone()
    return dict(row) if row else None


def list_samples(
    conn: sqlite3.Connection,
    *,
    hand_id: str | None = None,
    folio: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """List training samples with optional filters."""
    clauses: list[str] = []
    params: list[str | int] = []
    if hand_id:
        clauses.append("hand_id = ?")
        params.append(hand_id)
    if folio:
        clauses.append("folio = ?")
        params.append(folio)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM training_samples {where} ORDER BY folio, column_index, id"  # noqa: S608
        f" LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return per-hand counts: total, confirmed, skipped, pending."""
    rows = conn.execute(
        """
        SELECT hand_id,
               COUNT(*) AS total,
               SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN status = 'skipped'   THEN 1 ELSE 0 END) AS skipped,
               SUM(CASE WHEN status = 'pending'   THEN 1 ELSE 0 END) AS pending
        FROM training_samples
        GROUP BY hand_id
        """
    ).fetchall()
    return {r["hand_id"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

def upsert_chars(
    conn: sqlite3.Connection,
    sample_id: int,
    chars: list[dict],
) -> None:
    """Replace character records for a sample.

    Args:
        chars: List of dicts with keys: bbox [x1,y1,x2,y2], ocr_char, ocr_confidence.
    """
    conn.execute("DELETE FROM training_chars WHERE sample_id = ?", (sample_id,))
    conn.executemany(
        """
        INSERT INTO training_chars (sample_id, bbox_json, ocr_char, ocr_confidence)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                sample_id,
                json.dumps(c["bbox"]),
                c.get("ocr_char"),
                c.get("ocr_confidence"),
            )
            for c in chars
        ],
    )
    conn.commit()


def add_char(conn: sqlite3.Connection, sample_id: int, bbox: list[int]) -> int:
    """Insert a new character bbox for a sample. Returns the new row id."""
    cur = conn.execute(
        "INSERT INTO training_chars (sample_id, bbox_json, ocr_char, ocr_confidence)"
        " VALUES (?, ?, NULL, NULL)",
        (sample_id, json.dumps(bbox)),
    )
    conn.commit()
    return cur.lastrowid or 0


def delete_char(conn: sqlite3.Connection, char_id: int) -> None:
    """Delete a character bbox record."""
    conn.execute("DELETE FROM training_chars WHERE id = ?", (char_id,))
    conn.commit()


def save_char_label(conn: sqlite3.Connection, char_id: int, label: str) -> None:
    conn.execute(
        "UPDATE training_chars SET unicode_label = ? WHERE id = ?", (label, char_id)
    )
    conn.commit()


def update_char_bbox(conn: sqlite3.Connection, char_id: int, bbox: list[int]) -> None:
    """Update the bounding box of a single character record."""
    conn.execute(
        "UPDATE training_chars SET bbox_json = ? WHERE id = ?",
        (json.dumps(bbox), char_id),
    )
    conn.commit()


def get_chars(conn: sqlite3.Connection, sample_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM training_chars WHERE sample_id = ? ORDER BY id", (sample_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage the training database.")
    parser.add_argument("--init", action="store_true", help="Initialize schema (idempotent).")
    parser.add_argument("--db", type=Path, default=_DEFAULT_TRAINING_DB)
    args = parser.parse_args()

    if args.init:
        conn = get_training_connection(args.db)
        conn.close()
        print(f"Training database initialized: {args.db}")
    else:
        parser.print_help()
