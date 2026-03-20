"""IIIFManuscriptReader — reads manuscript folios via a IIIF Presentation API v2 manifest.

Images are downloaded on first access and cached locally under the manuscript's
data directory.  The OCR pipeline receives a local Path and has no knowledge of
the remote source.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from src.ocr.readers.base import ManuscriptReader

_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "manuscripts"
_REQUEST_DELAY = 0.5  # seconds between image downloads
_HEADERS = {"User-Agent": "aenigmata/0.1 (scholarly research)"}


class IIIFManuscriptReader(ManuscriptReader):
    """Reads folio images from a IIIF Presentation API v2 manifest.

    Args:
        manifest_url: URL of the IIIF manifest JSON.
        manuscript_id: Stable identifier used for local cache directory naming
                       (e.g. 'vat.gr.1209').
        image_size: IIIF size parameter for image requests.  Defaults to 'full'.
                    Use e.g. '2000,' to cap width at 2000 pixels.
    """

    def __init__(
        self,
        manifest_url: str,
        manuscript_id: str,
        image_size: str = "full",
    ) -> None:
        self._manifest_url = manifest_url
        self._manuscript_id = manuscript_id
        self._image_size = image_size
        self._base_dir = _CACHE_DIR / manuscript_id
        self._images_dir = self._base_dir / "images"
        self._manifest_path = self._base_dir / "manifest.json"
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._manifest: dict | None = None
        self._canvases: list[dict] | None = None

    # ------------------------------------------------------------------
    # ManuscriptReader interface
    # ------------------------------------------------------------------

    def get_manuscript_id(self) -> str:
        return self._manuscript_id

    def list_folios(self) -> list[str]:
        """Return folio labels in manuscript order."""
        return [self._canvas_label(c) for c in self._get_canvases()]

    def get_folio_image(self, folio_id: str) -> Path:
        """Return a local path to the folio image, downloading it if not cached."""
        dest = self._images_dir / f"{folio_id}.jpg"
        if dest.exists():
            return dest

        canvas = self._find_canvas(folio_id)
        url = self._image_url(canvas)
        if url is None:
            raise ValueError(f"No image URL found for folio {folio_id!r}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        response = self._session.get(url, timeout=60, stream=True)
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
        time.sleep(_REQUEST_DELAY)
        return dest

    def get_folio_metadata(self, folio_id: str) -> dict:
        """Return metadata for a folio extracted from the IIIF canvas."""
        canvas = self._find_canvas(folio_id)
        image_url = self._image_url(canvas)
        return {
            "folio_id": folio_id,
            "label": canvas.get("label", folio_id),
            "width": canvas.get("width"),
            "height": canvas.get("height"),
            "image_source_url": image_url,
            "canvas_id": canvas.get("@id") or canvas.get("id"),
            "manuscript_id": self._manuscript_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_manifest(self) -> dict:
        if self._manifest is not None:
            return self._manifest
        if self._manifest_path.exists():
            self._manifest = json.loads(
                self._manifest_path.read_text(encoding="utf-8")
            )
            return self._manifest
        response = self._session.get(self._manifest_url, timeout=30)
        response.raise_for_status()
        self._manifest = response.json()
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self._manifest

    def _get_canvases(self) -> list[dict]:
        if self._canvases is not None:
            return self._canvases
        manifest = self._get_manifest()
        canvases: list[dict] = []
        for sequence in manifest.get("sequences", []):
            canvases.extend(sequence.get("canvases", []))
        self._canvases = canvases
        return self._canvases

    def _find_canvas(self, folio_id: str) -> dict:
        for canvas in self._get_canvases():
            if self._canvas_label(canvas) == folio_id:
                return canvas
        raise KeyError(f"Folio {folio_id!r} not found in manifest")

    def _image_url(self, canvas: dict) -> str | None:
        for image in canvas.get("images", []):
            resource = image.get("resource", {})
            service = resource.get("service", {})
            service_id = service.get("@id") or service.get("id")
            if service_id:
                return f"{service_id.rstrip('/')}/full/{self._image_size}/0/default.jpg"
            resource_id = resource.get("@id") or resource.get("id")
            if resource_id:
                return resource_id
        return None

    @staticmethod
    def _canvas_label(canvas: dict) -> str:
        label = canvas.get("label", "unknown")
        if isinstance(label, dict):
            label = next(iter(label.values()), ["unknown"])[0]
        return str(label).strip().replace("/", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# Convenience factory for the Codex Vaticanus
# ---------------------------------------------------------------------------

def vaticanus_reader(image_size: str = "full") -> IIIFManuscriptReader:
    """Return a reader pre-configured for Codex Vaticanus (Vat.gr.1209)."""
    return IIIFManuscriptReader(
        manifest_url="https://digi.vatlib.it/iiif/MSS_Vat.gr.1209/manifest.json",
        manuscript_id="vat.gr.1209",
        image_size=image_size,
    )
