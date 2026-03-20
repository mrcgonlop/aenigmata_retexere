"""Extract line crops from OCR transcript JSON and populate the training database.

Each line from the transcript becomes one training sample:
  - The line bounding box is cropped from the folio image and saved as a PNG.
  - Character bboxes are detected via connected-component analysis (CCA) on the
    saved line image — this gives tight ink-based bboxes rather than Kraken's
    approximate cut positions.
  - The Kraken OCR guess is pre-filled as the starting transcription.

Usage:
    python -m src.training.extractor --manuscript vat.gr.1209 --folio 41
    python -m src.training.extractor --manuscript vat.gr.1209 --folio all
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from src.training.chardetect import detect_chars
from src.training.db import get_training_connection, insert_sample, upsert_chars

_DATA_DIR = Path("data")
_MANUSCRIPTS_DIR = _DATA_DIR / "manuscripts"
_TRAINING_IMAGES_DIR = _DATA_DIR / "training" / "images"

# Folios 1–40 belong to Hand A; 41+ to Hand B.
_HAND_A_THRESHOLD = 40


def _hand_for_folio(folio: str) -> str:
    """Return 'a', 'b', or 'unknown' based on folio number."""
    digits = "".join(c for c in folio if c.isdigit())
    if not digits:
        return "unknown"
    return "a" if int(digits) <= _HAND_A_THRESHOLD else "b"


def _find_folio_image(manuscript: str, folio: str) -> Path:
    """Locate the folio image, checking common extensions."""
    img_dir = _MANUSCRIPTS_DIR / manuscript / "images"
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        p = img_dir / f"{folio}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(
        f"No image found for folio '{folio}' in {img_dir}. "
        "Run scripts/download_vaticanus.py first."
    )


def extract_folio(
    manuscript: str,
    folio: str,
    transcript_path: Path | None = None,
    image_path: Path | None = None,
    pad: int = 4,
) -> int:
    """Extract and save line crops for one folio.

    Args:
        manuscript: Manuscript identifier (e.g. 'vat.gr.1209').
        folio: Folio identifier matching the transcript filename stem (e.g. '41').
        transcript_path: Override the default transcript location.
        image_path: Override the default folio image location.
        pad: Pixel padding added around each line crop (default 4).

    Returns:
        Number of new training samples inserted (existing ones are skipped).
    """
    # --- locate transcript ---
    if transcript_path is None:
        transcript_path = (
            _MANUSCRIPTS_DIR / manuscript / "transcripts" / f"{folio}.json"
        )
    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Transcript not found: {transcript_path}. "
            "Run: python -m src.ocr.recognize --manuscript {manuscript} --folio {folio} --save"
        )

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

    # --- locate folio image ---
    if image_path is None:
        image_path = _find_folio_image(manuscript, folio)

    folio_img = Image.open(image_path)
    img_w, img_h = folio_img.size

    _TRAINING_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    hand_id = _hand_for_folio(folio)
    conn = get_training_connection()

    # Prefer the first Kraken result (it has character-level bboxes).
    results: list[dict] = transcript.get("results", [])
    kraken_result = next(
        (r for r in results if r.get("engine", "").startswith("kraken")),
        results[0] if results else None,
    )
    if kraken_result is None:
        conn.close()
        return 0

    inserted = 0
    safe_manuscript = manuscript.replace(".", "_")

    for i, line in enumerate(kraken_result.get("lines", [])):
        bbox: list[int] | None = line.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(img_w, x2 + pad)
        y2 = min(img_h, y2 + pad)

        if x2 <= x1 or y2 <= y1:
            continue

        col = line.get("column", 0)
        filename = f"{safe_manuscript}_{folio}_col{col}_line{i:04d}.png"
        save_path = _TRAINING_IMAGES_DIR / filename

        crop = folio_img.crop((x1, y1, x2, y2))
        crop.save(save_path, format="PNG")

        sample_id = insert_sample(
            conn,
            manuscript=manuscript,
            folio=folio,
            hand_id=hand_id,
            line_image_path=filename,
            source_line_bbox=[x1, y1, x2, y2],
            column_index=col,
            ocr_guess=line.get("text"),
        )

        if sample_id:
            # Detect character bboxes via CCA on the saved line image.
            # This gives tight ink-based bboxes; Kraken's cut positions are
            # kept only as ocr_char hints for the labeler, not as bbox coords.
            cca_chars = detect_chars(save_path)
            if cca_chars:
                # Build char records — no ocr_char mapping (CCA is position-only)
                chars = [{"bbox": c["bbox"], "ocr_char": None, "ocr_confidence": None}
                         for c in cca_chars]
            elif line.get("chars"):
                # Fallback: use Kraken cuts (less accurate but better than nothing)
                chars = [
                    {
                        "bbox": [
                            ch.get("x1", x1) - x1,
                            ch.get("y1", y1) - y1,
                            ch.get("x2", x2) - x1,
                            ch.get("y2", y2) - y1,
                        ],
                        "ocr_char": ch.get("char"),
                        "ocr_confidence": ch.get("confidence"),
                    }
                    for ch in line["chars"]
                ]
            else:
                chars = []
            if chars:
                upsert_chars(conn, sample_id, chars)

        if sample_id:
            inserted += 1

    conn.close()
    return inserted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Extract line crops from OCR transcripts into the training database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.training.extractor --manuscript vat.gr.1209 --folio 41
  python -m src.training.extractor --manuscript vat.gr.1209 --folio all
        """,
    )
    parser.add_argument("--manuscript", required=True, metavar="ID")
    parser.add_argument(
        "--folio",
        required=True,
        metavar="FOLIO",
        help="Folio number, or 'all' to process every available transcript.",
    )
    args = parser.parse_args()

    if args.folio == "all":
        transcript_dir = _MANUSCRIPTS_DIR / args.manuscript / "transcripts"
        if not transcript_dir.exists():
            print(f"ERROR: no transcripts directory at {transcript_dir}", file=sys.stderr)
            sys.exit(1)
        folios = sorted(p.stem for p in transcript_dir.glob("*.json"))
        if not folios:
            print("No transcript JSON files found.", file=sys.stderr)
            sys.exit(1)
        total = 0
        for f in folios:
            n = extract_folio(args.manuscript, f)
            print(f"  folio {f}: {n} samples inserted")
            total += n
        print(f"\nTotal: {total} samples across {len(folios)} folios.")
    else:
        n = extract_folio(args.manuscript, args.folio)
        print(f"Inserted {n} training samples for folio {args.folio}.")
