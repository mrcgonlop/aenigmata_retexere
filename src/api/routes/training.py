"""Training data API routes.

Endpoints:
    GET  /api/training/stats                     — per-hand label progress
    GET  /api/training/lines                     — list samples (filters: hand, folio, status)
    GET  /api/training/lines/{id}                — single sample + char bboxes
    POST /api/training/lines/{id}/label          — save confirmed ground truth
    POST /api/training/lines/{id}/skip           — mark sample as skipped
    POST /api/training/chars/{char_id}/label     — label an individual character
    GET  /api/training/images/{filename}         — serve a line crop PNG
    POST /api/training/ingest                    — extract lines from an OCR transcript
    GET  /api/training/export                    — export confirmed labels to Kraken format
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.training import db as training_db
from src.training.export import export_hand
from src.training.extractor import extract_folio

router = APIRouter(tags=["training"])

_IMAGES_DIR = Path("data/training/images")


# ---------------------------------------------------------------------------
# Dependency: open + close a training DB connection per request
# ---------------------------------------------------------------------------

def _db():
    conn = training_db.get_training_connection()
    try:
        yield conn
    finally:
        conn.close()


# FastAPI doesn't support bare generator dependencies without Depends(),
# so we import Depends here and use it inline.
from fastapi import Depends  # noqa: E402

Db = Annotated[object, Depends(_db)]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LabelRequest(BaseModel):
    ground_truth: str


class CharLabelRequest(BaseModel):
    unicode_label: str


class BboxUpdateRequest(BaseModel):
    bbox: list[int]


class AddCharRequest(BaseModel):
    bbox: list[int]


class IngestRequest(BaseModel):
    manuscript: str
    folio: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/training/stats")
def get_stats(db: Db) -> dict:
    """Return labeled/total counts per scribal hand."""
    return training_db.get_stats(db)  # type: ignore[arg-type]


@router.get("/training/lines")
def list_lines(
    db: Db,
    hand: Annotated[str | None, Query()] = None,
    folio: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    return training_db.list_samples(  # type: ignore[arg-type]
        db,  # type: ignore[arg-type]
        hand_id=hand,
        folio=folio,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/training/lines/{sample_id}")
def get_line(sample_id: int, db: Db) -> dict:
    sample = training_db.get_sample(db, sample_id)  # type: ignore[arg-type]
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    chars = training_db.get_chars(db, sample_id)  # type: ignore[arg-type]
    # Deserialise bbox JSON strings for the frontend
    for c in chars:
        if isinstance(c.get("bbox_json"), str):
            c["bbox"] = json.loads(c["bbox_json"])
    sample["chars"] = chars
    sample["image_url"] = f"/api/training/images/{sample['line_image_path']}"
    return sample


@router.post("/training/lines/{sample_id}/label", status_code=204)
def label_line(sample_id: int, body: LabelRequest, db: Db) -> None:
    sample = training_db.get_sample(db, sample_id)  # type: ignore[arg-type]
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    training_db.save_label(db, sample_id, body.ground_truth)  # type: ignore[arg-type]


@router.post("/training/lines/{sample_id}/skip", status_code=204)
def skip_line(sample_id: int, db: Db) -> None:
    sample = training_db.get_sample(db, sample_id)  # type: ignore[arg-type]
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    training_db.skip_sample(db, sample_id)  # type: ignore[arg-type]


@router.post("/training/chars/{char_id}/label", status_code=204)
def label_char(char_id: int, body: CharLabelRequest, db: Db) -> None:
    training_db.save_char_label(db, char_id, body.unicode_label)  # type: ignore[arg-type]


@router.patch("/training/chars/{char_id}/bbox", status_code=204)
def update_char_bbox(char_id: int, body: BboxUpdateRequest, db: Db) -> None:
    if len(body.bbox) != 4:
        raise HTTPException(status_code=400, detail="bbox must be [x1, y1, x2, y2]")
    training_db.update_char_bbox(db, char_id, body.bbox)  # type: ignore[arg-type]


@router.post("/training/lines/{sample_id}/chars")
def add_char(sample_id: int, body: AddCharRequest, db: Db) -> dict:
    """Create a new character bbox for a sample (manual draw)."""
    if len(body.bbox) != 4:
        raise HTTPException(status_code=400, detail="bbox must be [x1, y1, x2, y2]")
    char_id = training_db.add_char(db, sample_id, body.bbox)  # type: ignore[arg-type]
    return {
        "id": char_id, "sample_id": sample_id,
        "bbox": body.bbox, "bbox_json": json.dumps(body.bbox),
        "ocr_char": None, "unicode_label": None, "ocr_confidence": None,
    }


@router.delete("/training/chars/{char_id}", status_code=204)
def delete_char(char_id: int, db: Db) -> None:
    """Delete a character bbox record."""
    training_db.delete_char(db, char_id)  # type: ignore[arg-type]


@router.get("/training/images/{filename}")
def serve_image(filename: str) -> FileResponse:
    """Serve a line crop PNG from data/training/images/."""
    # Sanitise: only allow simple filenames (no path traversal)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _IMAGES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png")


@router.post("/training/lines/{sample_id}/detect-chars")
def detect_chars_for_sample(sample_id: int, db: Db) -> dict:
    """Re-run CCA character detection on a saved line image and update training_chars."""
    from src.training.chardetect import detect_chars

    sample = training_db.get_sample(db, sample_id)  # type: ignore[arg-type]
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    image_path = _IMAGES_DIR / sample["line_image_path"]
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Line image not found on disk")

    chars = detect_chars(image_path)
    if not chars:
        return {"detected": 0, "note": "No characters detected — check image quality"}

    char_records = [
        {"bbox": c["bbox"], "ocr_char": None, "ocr_confidence": None}
        for c in chars
    ]
    training_db.upsert_chars(db, sample_id, char_records)  # type: ignore[arg-type]
    return {"detected": len(chars)}


@router.post("/training/ingest")
def ingest(body: IngestRequest) -> dict:
    """Extract line crops from an OCR transcript and insert into the training DB."""
    try:
        n = extract_folio(body.manuscript, body.folio)
        return {"inserted": n, "manuscript": body.manuscript, "folio": body.folio}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/training/export")
def trigger_export(
    hand: Annotated[str, Query()] = "b",
    eval_split: Annotated[float, Query(ge=0.0, le=0.5)] = 0.10,
) -> dict:
    """Export confirmed labels for a given hand to Kraken training format."""
    if hand not in ("a", "b", "unknown", "all"):
        raise HTTPException(status_code=400, detail="hand must be a, b, unknown, or all")
    hands = ["a", "b", "unknown"] if hand == "all" else [hand]
    results = {}
    for h in hands:
        results[f"hand_{h}"] = export_hand(h, eval_split=eval_split)
    return results
