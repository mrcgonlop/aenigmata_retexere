"""OCR feasibility evaluation for Codex Vaticanus folios.

Runs multiple OCR engines on a single folio image with different preprocessing
strategies and prints a side-by-side comparison.  If a reference text is
provided, also computes Character Error Rate (CER) for each engine.

Usage examples:
    # List all downloaded folios
    python scripts/evaluate_ocr.py --list

    # Run on a specific folio by label
    python scripts/evaluate_ocr.py --folio 1r

    # Run on a specific image file directly
    python scripts/evaluate_ocr.py --image data/manuscripts/vat.gr.1209/images/1r.jpg

    # Compare against a known reference string
    python scripts/evaluate_ocr.py --folio 1r --reference "ΕΝΑΡΧΗΗΝΟΛΟΓΟΣ"

    # Save preprocessed debug images alongside OCR output
    python scripts/evaluate_ocr.py --folio 1r --save-debug debug/

    # Add Kraken recognition (requires a downloaded model)
    python scripts/evaluate_ocr.py --folio 1r --kraken-model path/to/model.mlmodel

Setup checklist:
    pip install -e ".[dev]"
    pip install pytesseract pillow easyocr   # OCR backends
    # Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki
    # Tesseract grc pack: included in the above installer (select "Greek Ancient")
    # Kraken model (optional): kraken list | grep -i greek  then  kraken get <id>
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
MANUSCRIPT_DIR = ROOT / "data" / "manuscripts" / "vat.gr.1209"
IMAGES_DIR = MANUSCRIPT_DIR / "images"
MANIFEST_PATH = MANUSCRIPT_DIR / "manifest.json"

# ---------------------------------------------------------------------------
# Known reference passages (normalized: uppercase, no diacritics, no spaces)
# Useful for CER evaluation without needing to type the full text.
# ---------------------------------------------------------------------------

KNOWN_PASSAGES: dict[str, str] = {
    # John 1:1-5 (uncial, scriptio continua, no word breaks)
    "john_1_1": "ΕΝΑΡΧΗΗΝΟΛΟΓΟΣΚΑΙΟΛΟΓΟΣΗΝΠΡΟΣΤΟΝΘΕΟΝΚΑΙΘΕΟΣΗΝΟΛΟΓΟΣ",
    "john_1_1_5": (
        "ΕΝΑΡΧΗΗΝΟΛΟΓΟΣΚΑΙΟΛΟΓΟΣΗΝΠΡΟΣΤΟΝΘΕΟΝΚΑΙΘΕΟΣΗΝΟΛΟΓΟΣ"
        "ΟΥΤΟΣΗΝΕΝΑΡΧΗΠΡΟΣΤΟΝΘΕΟΝ"
        "ΠΑΝΤΑΔΙΑΥΤΟΥΕΓΕΝΕΤΟΚΑΙΧΩΡΙΣΑΥΤΟΥΕΓΕΝΕΤΟΟΥΔΕΕΝ"
        "ΟΓΕΓΟΝΕΝΕΝΑΥΤΩΖΩΗΗΝΚΑΙΗΖΩΗΗΝΤΟΦΩΣΤΩΝΑΝΘΡΩΠΩΝ"
        "ΚΑΙΤΟΦΩΣΕΝΤΗΣΚΟΤΙΑΦΑΙΝΕΙΚΑΙΗΣΚΟΤΙΑΑΥΤΟΟΥΚΑΤΕΛΑΒΕΝ"
    ),
}

# ---------------------------------------------------------------------------
# Unicode normalization for CER
# ---------------------------------------------------------------------------

def normalize_for_cer(text: str) -> str:
    """Strip diacritics, uppercase, keep only Greek letters.

    Both the OCR output (likely polytonic with accents) and the reference
    (plain uncial uppercase) are normalized to bare uppercase Greek letters
    before CER is computed.
    """
    # NFD splits characters from their combining diacritics
    decomposed = unicodedata.normalize("NFD", text)
    greek = "".join(
        c for c in decomposed
        if unicodedata.category(c) != "Mn"          # drop combining marks
        and ("\u0370" <= c <= "\u03FF"               # Greek and Coptic block
             or "\u1F00" <= c <= "\u1FFF")           # Greek Extended block
    )
    return greek.upper()


# ---------------------------------------------------------------------------
# CER computation (simple Levenshtein)
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev = dp[0]
        dp[0] = i
        for j, cb in enumerate(b, 1):
            temp = dp[j]
            dp[j] = prev if ca == cb else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[len(b)]


def character_error_rate(hypothesis: str, reference: str) -> float:
    """CER = edit_distance(normalized_hyp, normalized_ref) / len(normalized_ref)."""
    hyp = normalize_for_cer(hypothesis)
    ref = normalize_for_cer(reference)
    if not ref:
        return 0.0
    return levenshtein(hyp, ref) / len(ref)


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(
            f"Manifest not found at {MANIFEST_PATH}.\n"
            "Run:  python scripts/download_vaticanus.py --dry-run\n"
            "to fetch the manifest first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def list_folios(manifest: dict) -> list[tuple[str, str]]:
    """Return [(label, canvas_id), ...] for every canvas in the manifest."""
    result = []
    for seq in manifest.get("sequences", []):
        for canvas in seq.get("canvases", []):
            label = canvas.get("label", "?")
            if isinstance(label, dict):
                label = next(iter(label.values()), ["?"])[0]
            label = str(label).strip()
            result.append((label, canvas.get("@id", "")))
    return result


def find_image(folio_label: str) -> Path:
    """Locate the downloaded image for a folio label."""
    safe = folio_label.replace("/", "_").replace(" ", "_")
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        p = IMAGES_DIR / f"{safe}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Image for folio '{folio_label}' not found in {IMAGES_DIR}.\n"
        f"Run:  python scripts/download_vaticanus.py --folios 1 --start {folio_label!r}"
    )


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

SEPARATOR = "─" * 72


def print_section(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def print_result(result, reference: str | None = None) -> None:  # type: ignore[no-untyped-def]
    print(str(result))
    if reference and result.available and not result.error and result.text:
        cer = character_error_rate(result.text, reference)
        norm_ref = normalize_for_cer(reference)
        norm_hyp = normalize_for_cer(result.text)
        print(f"  CER vs reference: {cer:.1%}  "
              f"({len(norm_hyp)} chars recognized / {len(norm_ref)} in reference)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--folio", metavar="LABEL",
                       help="Folio label as it appears in the manifest (e.g. '1r')")
    group.add_argument("--image", metavar="PATH", type=Path,
                       help="Direct path to any folio image file")
    group.add_argument("--list", action="store_true",
                       help="List all available folio labels from the manifest")

    parser.add_argument("--reference", metavar="TEXT_OR_KEY",
                        help=(
                            "Reference text for CER computation.  Can be a plain string "
                            "or one of the built-in keys: " + ", ".join(KNOWN_PASSAGES)
                        ))
    parser.add_argument("--kraken-model", metavar="PATH", type=Path,
                        help="Path to a Kraken .mlmodel recognition model")
    parser.add_argument("--save-debug", metavar="DIR", type=Path,
                        help="Save preprocessed images to this directory for inspection")
    parser.add_argument("--max-width", type=int, default=3000,
                        help="Max image width before downscaling (default: 3000)")
    args = parser.parse_args()

    # ── --list ──────────────────────────────────────────────────────────────
    if args.list:
        manifest = load_manifest()
        folios = list_folios(manifest)
        print(f"Manifest contains {len(folios)} folios:\n")
        downloaded = set(p.stem for p in IMAGES_DIR.glob("*") if p.is_file())
        for label, _ in folios:
            safe = label.replace("/", "_").replace(" ", "_")
            status = "✓" if safe in downloaded else "·"
            print(f"  {status}  {label}")
        print(f"\n✓ = image downloaded  · = not yet downloaded")
        print(f"\nDownloaded: {len(downloaded)}/{len(folios)}")
        return

    # ── resolve image path ───────────────────────────────────────────────────
    if args.image:
        img_path = args.image.resolve()
        folio_label = img_path.stem
    elif args.folio:
        img_path = find_image(args.folio)
        folio_label = args.folio
    else:
        parser.print_help()
        sys.exit(0)

    if not img_path.exists():
        print(f"Image not found: {img_path}", file=sys.stderr)
        sys.exit(1)

    # ── resolve reference ────────────────────────────────────────────────────
    reference: str | None = None
    if args.reference:
        reference = KNOWN_PASSAGES.get(args.reference, args.reference)
        print(f"Reference ({len(normalize_for_cer(reference))} chars after normalization):")
        print(f"  {normalize_for_cer(reference)[:80]}{'…' if len(normalize_for_cer(reference)) > 80 else ''}")

    # ── import pipeline ──────────────────────────────────────────────────────
    try:
        from src.ocr.preprocess import preprocess
        from src.ocr import recognize
    except ImportError as exc:
        print(f"Import error: {exc}\nRun from the project root: python scripts/evaluate_ocr.py",
              file=sys.stderr)
        sys.exit(1)

    print(f"\naenigmata OCR Evaluation")
    print(f"Folio : {folio_label}")
    print(f"Image : {img_path}")
    print(f"Size  : {img_path.stat().st_size // 1024} KB")

    # ── preprocessing variants ───────────────────────────────────────────────
    debug_dir = args.save_debug
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    configs: list[tuple[str, dict]] = [
        ("raw_gray",  dict(binarize_method="none",     do_deskew=False)),
        ("deskewed",  dict(binarize_method="none",     do_deskew=True)),
        ("adaptive",  dict(binarize_method="adaptive", do_deskew=True)),
        ("otsu",      dict(binarize_method="otsu",     do_deskew=True)),
    ]

    preprocessed: dict[str, object] = {}
    print_section("Preprocessing")
    for name, cfg in configs:
        img_arr, info = preprocess(img_path, max_width=args.max_width, **cfg)
        preprocessed[name] = img_arr
        print(f"  {name:<12}  {info['processed_size'][0]}×{info['processed_size'][1]}px"
              f"  deskew={info['deskew_angle_deg']:+.2f}°"
              f"  method={info['binarize_method']}")
        if debug_dir:
            import cv2
            out = debug_dir / f"{folio_label}_{name}.png"
            cv2.imwrite(str(out), img_arr)
            print(f"              → saved {out}")

    # ── Tesseract ────────────────────────────────────────────────────────────
    print_section("Tesseract — Ancient Greek (grc)")
    for name in ("raw_gray", "adaptive", "otsu"):
        result = recognize.tesseract(preprocessed[name], lang="grc", psm=6)
        result.engine = f"tesseract[grc|{name}]"
        print_result(result, reference)

    print_section("Tesseract — Modern Greek (ell) for comparison")
    result = recognize.tesseract(preprocessed["adaptive"], lang="ell", psm=6)
    result.engine = "tesseract[ell|adaptive]"
    print_result(result, reference)

    # ── EasyOCR ──────────────────────────────────────────────────────────────
    print_section("EasyOCR — Modern Greek (el)")
    result = recognize.easyocr(preprocessed["adaptive"], langs=["el"])
    print_result(result, reference)

    # ── Kraken ───────────────────────────────────────────────────────────────
    print_section("Kraken")
    result = recognize.kraken(img_path, model_path=args.kraken_model)
    print_result(result, reference)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print("  Done.")
    if debug_dir:
        print(f"  Preprocessed images saved to: {debug_dir}")
    print(SEPARATOR)
    print()


if __name__ == "__main__":
    main()
