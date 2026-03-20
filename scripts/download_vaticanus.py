"""Download Codex Vaticanus (Vat.gr.1209) folio images from the Vatican Digital Library.

The Vatican Digital Library exposes this manuscript via IIIF Presentation API v2.
Images are downloaded to data/manuscripts/vat.gr.1209/images/ and are gitignored
(large binary files). The manifest metadata is saved to
data/manuscripts/vat.gr.1209/manifest.json and IS committed.

Usage:
    python scripts/download_vaticanus.py [--size SIZE] [--folios N] [--start LABEL]

Options:
    --size SIZE     IIIF size parameter, e.g. "full", "2000," (width), "1000,"
                    Defaults to "full" (maximum available resolution).
    --folios N      Download only the first N folios (useful for testing).
    --start LABEL   Start from this folio label (e.g. "1r"), skipping earlier ones.
    --dry-run       Print folio list without downloading.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

MANIFEST_URL = "https://digi.vatlib.it/iiif/MSS_Vat.gr.1209/manifest.json"
MANUSCRIPT_ID = "vat.gr.1209"
OUT_DIR = Path(__file__).parent.parent / "data" / "manuscripts" / MANUSCRIPT_ID
IMAGES_DIR = OUT_DIR / "images"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# Be a respectful client: pause between image requests.
REQUEST_DELAY_SECONDS = 1.0
SESSION_HEADERS = {
    "User-Agent": "aenigmata/0.1 (https://github.com/aenigmata; scholarly research)"
}


def fetch_manifest(session: requests.Session) -> dict:
    """Fetch and return the IIIF manifest, caching it to disk."""
    if MANIFEST_PATH.exists():
        print(f"Using cached manifest at {MANIFEST_PATH}")
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    print(f"Fetching manifest from {MANIFEST_URL} …")
    response = session.get(MANIFEST_URL, timeout=30)
    response.raise_for_status()
    manifest = response.json()

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Manifest saved to {MANIFEST_PATH}")
    return manifest


def extract_canvases(manifest: dict) -> list[dict]:
    """Return a flat list of canvas dicts from a IIIF v2 manifest."""
    canvases = []
    for sequence in manifest.get("sequences", []):
        canvases.extend(sequence.get("canvases", []))
    return canvases


def image_url(canvas: dict, size: str) -> str | None:
    """Extract the IIIF image URL for a canvas at the requested size.

    Tries the IIIF Image API service first; falls back to the resource @id.
    """
    for image in canvas.get("images", []):
        resource = image.get("resource", {})
        service = resource.get("service", {})
        service_id = service.get("@id") or service.get("id")
        if service_id:
            service_id = service_id.rstrip("/")
            return f"{service_id}/full/{size}/0/default.jpg"
        # Fallback: direct resource URL (may not honour size parameter)
        resource_id = resource.get("@id") or resource.get("id")
        if resource_id:
            return resource_id
    return None


def folio_label(canvas: dict) -> str:
    """Return the human-readable folio label, sanitised for use as a filename."""
    label = canvas.get("label", "unknown")
    # Label may be a plain string or a IIIF v3-style {"en": [...]} object.
    if isinstance(label, dict):
        label = next(iter(label.values()), ["unknown"])[0]
    # Sanitise for filesystem: replace spaces and slashes.
    return str(label).strip().replace("/", "_").replace(" ", "_")


def download_folio(
    session: requests.Session,
    canvas: dict,
    size: str,
    dry_run: bool,
) -> bool:
    """Download a single folio image. Returns True if downloaded, False if skipped."""
    label = folio_label(canvas)
    url = image_url(canvas, size)
    if url is None:
        print(f"  [WARN] No image URL found for folio {label!r}, skipping.")
        return False

    dest = IMAGES_DIR / f"{label}.jpg"

    if dry_run:
        print(f"  {label:>10}  →  {url}")
        return False

    if dest.exists():
        print(f"  {label:>10}  already exists, skipping.")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {label:>10}  downloading … ", end="", flush=True)
    try:
        response = session.get(url, timeout=60, stream=True)
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"done ({size_kb} KB)")
        return True
    except requests.HTTPError as exc:
        print(f"HTTP error {exc.response.status_code}")
        return False
    except requests.RequestException as exc:
        print(f"request error: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--size",
        default="full",
        help='IIIF size parameter (default: "full"). Use e.g. "2000," for 2000px wide.',
    )
    parser.add_argument(
        "--folios",
        type=int,
        default=None,
        metavar="N",
        help="Download only the first N folios.",
    )
    parser.add_argument(
        "--start",
        default=None,
        metavar="LABEL",
        help="Start from this folio label, skipping earlier ones.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print folio list and image URLs without downloading.",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(SESSION_HEADERS)

    try:
        manifest = fetch_manifest(session)
    except requests.RequestException as exc:
        print(f"Failed to fetch manifest: {exc}", file=sys.stderr)
        sys.exit(1)

    canvases = extract_canvases(manifest)
    if not canvases:
        print("No canvases found in manifest.", file=sys.stderr)
        sys.exit(1)

    print(f"\nManifest contains {len(canvases)} folios.")

    # Apply --start filter.
    if args.start:
        labels = [folio_label(c) for c in canvases]
        if args.start not in labels:
            print(f"Label {args.start!r} not found in manifest.", file=sys.stderr)
            sys.exit(1)
        start_idx = labels.index(args.start)
        canvases = canvases[start_idx:]
        print(f"Starting from folio {args.start!r} ({len(canvases)} remaining).")

    # Apply --folios limit.
    if args.folios is not None:
        canvases = canvases[: args.folios]
        print(f"Limiting to first {args.folios} folios.")

    print(f"\nDownloading {len(canvases)} folios at size={args.size!r}:\n")
    downloaded = skipped = errors = 0

    for i, canvas in enumerate(canvases):
        result = download_folio(session, canvas, args.size, args.dry_run)
        if result:
            downloaded += 1
            # Pause between downloads to respect the server.
            if i < len(canvases) - 1:
                time.sleep(REQUEST_DELAY_SECONDS)
        else:
            skipped += 1

    if not args.dry_run:
        print(f"\nDone. Downloaded: {downloaded}  Skipped: {skipped}  Errors: {errors}")
        print(f"Images saved to: {IMAGES_DIR}")


if __name__ == "__main__":
    main()
