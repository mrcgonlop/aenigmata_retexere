"""Multi-engine OCR recognition for manuscript folios.

Each engine function accepts a preprocessed numpy image and returns a
RecognitionResult.  Engines are imported lazily so the module is importable
even if a given backend is not installed.

CLI usage:
    python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 1
    python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 1 --engine tesseract
    python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 1 --engine kraken --kraken-model path/to/model.mlmodel
    python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 1 --save
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class CharResult:
    """Per-character OCR output with position in image coordinates."""
    char: str
    x1: int
    x2: int
    y1: int
    y2: int
    confidence: float | None = None


@dataclass
class LineResult:
    """Per-line OCR output with spatial metadata."""
    bbox: list[int]                       # [x1, y1, x2, y2] in image pixels
    text: str
    confidence: float | None = None       # average character confidence, 0–1
    column: int = 0                       # column index (0-based), 0 when not split
    chars: list[CharResult] = field(default_factory=list)


@dataclass
class RecognitionResult:
    engine: str
    text: str
    elapsed_ms: float
    available: bool = True
    error: str | None = None
    lines: list[LineResult] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.available:
            return f"[{self.engine}] NOT AVAILABLE: {self.error}"
        if self.error:
            return f"[{self.engine}] ERROR: {self.error}"
        text_lines = self.text.splitlines()
        preview = "\n".join(f"  {ln}" for ln in text_lines[:6])
        suffix = f"\n  … ({len(text_lines)} lines total)" if len(text_lines) > 6 else ""
        return f"[{self.engine}] ({self.elapsed_ms:.0f} ms)\n{preview}{suffix}"


# ---------------------------------------------------------------------------
# Tesseract
# ---------------------------------------------------------------------------

def tesseract(
    img: np.ndarray,
    lang: str = "grc",
    psm: int = 6,
) -> RecognitionResult:
    """Run Tesseract on a preprocessed numpy image.

    Args:
        img: Grayscale or binary uint8 array.
        lang: Tesseract language code.  'grc' = ancient Greek polytonic.
              'ell' = modern Greek (fallback if grc pack not installed).
        psm: Page segmentation mode.  6 = assume a uniform block of text
             (good for a manuscript column); 3 = fully automatic.

    Requirements:
        - pip install pytesseract pillow
        - Tesseract binary on PATH (https://github.com/UB-Mannheim/tesseract/wiki)
        - tesseract-ocr-grc language pack installed
    """
    try:
        import pytesseract
        from PIL import Image as PILImage
    except ImportError:
        return RecognitionResult(
            engine=f"tesseract[{lang}]", text="", elapsed_ms=0,
            available=False, error="pip install pytesseract pillow",
        )

    t0 = time.perf_counter()
    try:
        pil = PILImage.fromarray(img)
        config = f"--psm {psm} --oem 1"
        text = pytesseract.image_to_string(pil, lang=lang, config=config)
        elapsed = (time.perf_counter() - t0) * 1000
        return RecognitionResult(
            engine=f"tesseract[{lang}|psm={psm}]",
            text=text.strip(),
            elapsed_ms=elapsed,
        )
    except pytesseract.TesseractNotFoundError:
        return RecognitionResult(
            engine=f"tesseract[{lang}]", text="", elapsed_ms=0,
            available=False,
            error="Tesseract binary not found. Install from https://github.com/UB-Mannheim/tesseract/wiki",
        )
    except Exception as exc:
        return RecognitionResult(
            engine=f"tesseract[{lang}]", text="", elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Kraken
# ---------------------------------------------------------------------------

def _records_to_lines(
    records: list[Any],
    col_idx: int = 0,
    x_offset: int = 0,
) -> list[LineResult]:
    """Convert a list of Kraken OCR records into LineResult objects.

    Args:
        records: BBoxOCRRecord or BaselineOCRRecord instances from rpred.
        col_idx: Column index (0-based) these records came from.
        x_offset: Horizontal pixel offset to add to all x-coordinates when
                  records were produced from a cropped column sub-image.
    """
    line_results: list[LineResult] = []
    for rec in records:
        raw_bbox = list(rec.bbox) if hasattr(rec, "bbox") and rec.bbox is not None else []
        if x_offset and len(raw_bbox) == 4:
            bbox = [raw_bbox[0] + x_offset, raw_bbox[1], raw_bbox[2] + x_offset, raw_bbox[3]]
        else:
            bbox = raw_bbox

        confs = rec.confidences or []
        avg_conf = float(sum(confs) / len(confs)) if confs else None

        # Extract character-level positions from cuts.
        # Each cut is the LEFT boundary of the character as a quadrilateral.
        # Character i spans from cuts[i][0][0] to cuts[i+1][0][0] horizontally.
        chars: list[CharResult] = []
        cuts = rec.cuts or []
        y1 = bbox[1] if len(bbox) >= 4 else 0
        y2 = bbox[3] if len(bbox) >= 4 else 0
        for ci, ch in enumerate(rec.prediction):
            if ci >= len(cuts):
                break
            cx1 = cuts[ci][0][0] + x_offset
            cx2 = (cuts[ci + 1][0][0] + x_offset) if ci + 1 < len(cuts) else (bbox[2] if bbox else cx1)
            ch_conf = float(confs[ci]) if ci < len(confs) else None
            chars.append(CharResult(char=ch, x1=cx1, x2=cx2, y1=y1, y2=y2, confidence=ch_conf))

        line_results.append(LineResult(
            bbox=bbox,
            text=rec.prediction,
            confidence=avg_conf,
            column=col_idx,
            chars=chars,
        ))
    return line_results


def kraken(
    img_path: Path,
    model_path: Path | None = None,
    bbox_scale: float = 30,
    columns: int = 1,
) -> RecognitionResult:
    """Run Kraken OCR on a folio image, with optional column splitting.

    The segmentation method is automatically selected from the model's seg_type:
    - 'bbox' models: nlbin binarization + pageseg (legacy line detection)
    - 'baselines' models: BLLA (modern baseline layout analysis)

    When columns > 1, the image is split at auto-detected column boundaries
    (via vertical ink-density projection) and each column is processed
    independently, producing cleaner line detection for multi-column manuscripts.

    Args:
        img_path: Path to the folio image.
        model_path: Path to a Kraken .mlmodel recognition model.
        bbox_scale: Expected line height in pixels for pageseg (default 30).
        columns: Number of text columns on the page (default 1).
                 Set to 3 for the Codex Vaticanus.

    Requirements:
        - pip install kraken
    """
    try:
        import kraken.binarization as _binarization
        import kraken.blla as _blla
        import kraken.pageseg as _pageseg
        from kraken import rpred as _rpred
        from kraken.lib import models as _kmodels
        from kraken.lib import vgsl as _vgsl
        from PIL import Image as PILImage
    except ImportError as exc:
        return RecognitionResult(engine="kraken", text="", elapsed_ms=0,
                                 available=False, error=str(exc))

    if model_path is None:
        return RecognitionResult(
            engine="kraken", text="", elapsed_ms=0, available=False,
            error=(
                "No recognition model specified (--kraken-model PATH).\n"
                "  Find Greek models: PYTHONIOENCODING=utf-8 kraken list\n"
                "  Download one:      kraken get <model-id>\n"
                "  Or search:         https://zenodo.org (search 'Kraken ancient Greek')"
            ),
        )

    t0 = time.perf_counter()
    try:
        from src.ocr.preprocess import detect_columns, split_columns

        recog_model = _kmodels.load_any(str(model_path))
        seg_type = getattr(recog_model, "seg_type", "baselines")

        gray_full = PILImage.open(img_path).convert("L")

        # Detect column split points from the binarized image.
        import numpy as np
        binary_np = np.array(_binarization.nlbin(gray_full))
        col_separators = detect_columns(binary_np, num_cols=columns) if columns > 1 else []

        # Build list of (PIL column image, x_offset) pairs.
        if col_separators:
            col_images = split_columns(gray_full, col_separators)
            x_offsets = [0] + col_separators
        else:
            col_images = [gray_full]
            x_offsets = [0]

        line_results: list[LineResult] = []

        for col_idx, (col_img, x_off) in enumerate(zip(col_images, x_offsets)):
            if seg_type == "bbox":
                binary_col = _binarization.nlbin(col_img)
                seg = _pageseg.segment(binary_col, scale=bbox_scale)
                records = list(_rpred.rpred(recog_model, binary_col, seg))
            else:
                rgb_col = col_img.convert("RGB")
                blla_model = Path(_blla.__file__).parent / "blla.mlmodel"
                seg_model = _vgsl.TorchVGSLModel.load_model(str(blla_model))
                seg = _blla.segment(rgb_col, model=seg_model)
                records = list(_rpred.rpred(recog_model, rgb_col, seg))

            line_results.extend(_records_to_lines(records, col_idx=col_idx, x_offset=x_off))

        # Sort all lines by reading order: column first, then top-to-bottom within column.
        line_results.sort(key=lambda lr: (lr.column, lr.bbox[1] if lr.bbox else 0))

        elapsed = (time.perf_counter() - t0) * 1000
        return RecognitionResult(
            engine=f"kraken[{seg_type}]{'×' + str(columns) + 'col' if columns > 1 else ''}",
            text="\n".join(r.text for r in line_results),
            elapsed_ms=elapsed,
            lines=line_results,
        )
    except Exception as exc:
        return RecognitionResult(
            engine="kraken", text="", elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# EasyOCR (Greek support via 'el' — modern Greek, worth trying)
# ---------------------------------------------------------------------------

def easyocr(
    img: np.ndarray,
    langs: list[str] | None = None,
) -> RecognitionResult:
    """Run EasyOCR on a preprocessed numpy image.

    EasyOCR does not have an ancient Greek model, but its modern Greek ('el')
    model covers the same alphabet and may handle uncial letterforms better
    than Tesseract in some cases.  Worth comparing.

    Requirements:
        - pip install easyocr  (pulls in PyTorch — large install)
    """
    langs = langs or ["el"]
    try:
        import easyocr as _easyocr
    except ImportError:
        return RecognitionResult(
            engine=f"easyocr{langs}", text="", elapsed_ms=0,
            available=False, error="pip install easyocr",
        )

    t0 = time.perf_counter()
    try:
        reader = _easyocr.Reader(langs, gpu=False, verbose=False)
        results = reader.readtext(img, detail=0, paragraph=False)
        text = "\n".join(results)
        elapsed = (time.perf_counter() - t0) * 1000
        return RecognitionResult(engine=f"easyocr{langs}", text=text, elapsed_ms=elapsed)
    except Exception as exc:
        return RecognitionResult(
            engine=f"easyocr{langs}", text="", elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    from src.ocr.preprocess import preprocess
    from src.ocr.readers import LocalManuscriptReader

    _DATA_DIR = Path(__file__).parent.parent.parent / "data"
    _MANUSCRIPTS_DIR = _DATA_DIR / "manuscripts"

    parser = argparse.ArgumentParser(
        description="Run OCR on a manuscript folio.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Kraken, 3-column Vaticanus, save transcript + open labeling tool:
  python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 41 \\
      --engine kraken --kraken-model data/models/model_grc_catlips.mlmodel \\
      --columns 3 --save --label

  # Single-column, no labeling:
  python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 41 \\
      --engine kraken --kraken-model data/models/model_grc_catlips.mlmodel --save

Output folders (relative to data/manuscripts/{id}/):
  transcripts/{folio}.json   — structured OCR output with per-line bboxes & chars
  labels/{folio}.html        — standalone labeling interface (--label flag)
        """,
    )
    parser.add_argument("--manuscript", required=True, metavar="ID",
                        help="Manuscript identifier, e.g. vat.gr.1209")
    parser.add_argument("--folio", required=True, metavar="FOLIO",
                        help="Folio label matching the image filename stem, e.g. 41 or 123r")
    parser.add_argument("--engine", default="kraken",
                        choices=["tesseract", "kraken", "easyocr", "all"],
                        help="OCR engine to use (default: kraken)")
    parser.add_argument("--kraken-model", type=Path,
                        default=Path("data/models/model_grc_catlips.mlmodel"), metavar="PATH",
                        help="Path to Kraken .mlmodel (default: data/models/model_grc_catlips.mlmodel)")
    parser.add_argument("--columns", type=int, default=3, metavar="N",
                        help="Number of text columns per page (default: 3 for Codex Vaticanus)")
    parser.add_argument("--bbox-scale", type=float, default=30, metavar="N",
                        help="pageseg line-height hint in px (default: 30)")
    parser.add_argument("--lang", default="grc",
                        help="Tesseract language code (default: grc)")
    parser.add_argument("--binarize", default="adaptive",
                        choices=["adaptive", "otsu", "none"],
                        help="Preprocessing binarization method (default: adaptive)")
    parser.add_argument("--save", action="store_true",
                        help="Save transcript JSON to data/manuscripts/{id}/transcripts/{folio}.json")
    parser.add_argument("--label", action="store_true",
                        help="Generate standalone HTML labeling interface to data/manuscripts/{id}/labels/{folio}.html")
    args = parser.parse_args()

    manuscript_dir = _MANUSCRIPTS_DIR / args.manuscript
    if not manuscript_dir.exists():
        print(f"ERROR: manuscript directory not found: {manuscript_dir}", file=sys.stderr)
        sys.exit(1)

    reader = LocalManuscriptReader(manuscript_dir, args.manuscript)
    try:
        img_path = reader.get_folio_image(args.folio)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        available = reader.list_folios()
        print(f"Available folios: {available[:10]}{'...' if len(available) > 10 else ''}", file=sys.stderr)
        sys.exit(1)

    print(f"Image: {img_path}")
    processed, info = preprocess(img_path, binarize_method=args.binarize)
    print(f"Preprocessed: {info['processed_size'][0]}x{info['processed_size'][1]}px  "
          f"skew={info['deskew_angle_deg']:.2f}°")
    print()

    results: list[RecognitionResult] = []
    engines = ["tesseract", "kraken", "easyocr"] if args.engine == "all" else [args.engine]

    for engine_name in engines:
        if engine_name == "tesseract":
            result = tesseract(processed, lang=args.lang)
        elif engine_name == "kraken":
            result = kraken(img_path, model_path=args.kraken_model,
                            bbox_scale=args.bbox_scale, columns=args.columns)
        else:
            result = easyocr(processed)
        results.append(result)
        print(result)
        print()

    if args.save or args.label:
        transcript_dir = manuscript_dir / "transcripts"
        transcript_dir.mkdir(exist_ok=True)
        out_path = transcript_dir / f"{args.folio}.json"

        payload = {
            "manuscript": args.manuscript,
            "folio": args.folio,
            "image": str(img_path),
            "preprocessing": info,
            "results": [
                {
                    "engine": r.engine,
                    "text": r.text,
                    "elapsed_ms": r.elapsed_ms,
                    "available": r.available,
                    "error": r.error,
                    "lines": [
                        {
                            "bbox": ln.bbox,
                            "text": ln.text,
                            "confidence": round(ln.confidence, 4) if ln.confidence is not None else None,
                            "column": ln.column,
                            "chars": [
                                {
                                    "char": c.char,
                                    "x1": c.x1, "x2": c.x2,
                                    "y1": c.y1, "y2": c.y2,
                                    "confidence": round(c.confidence, 4) if c.confidence is not None else None,
                                }
                                for c in ln.chars
                            ],
                        }
                        for ln in r.lines
                    ],
                }
                for r in results
            ],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Transcript: {out_path}")

    if args.label:
        import subprocess
        import webbrowser
        label_script = Path(__file__).parent.parent.parent / "scripts" / "label_ocr.py"
        subprocess.run(
            [sys.executable, str(label_script),
             "--manuscript", args.manuscript,
             "--folio", args.folio],
            check=True,
        )
        html_path = _MANUSCRIPTS_DIR / args.manuscript / "labels" / f"{args.folio}.html"
        webbrowser.open(html_path.as_uri())
