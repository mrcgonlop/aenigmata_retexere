"""LocalManuscriptReader — reads folio images from a local directory.

Expects images named after folio identifiers with a common extension:
    <images_dir>/<folio_id>.<ext>

A manifest.json file in the manuscript directory (if present) is used for
metadata; otherwise metadata is inferred from the filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.ocr.readers.base import ManuscriptReader

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")


class LocalManuscriptReader(ManuscriptReader):
    """Reads folio images from a local directory.

    Args:
        manuscript_dir: Path to the manuscript directory, e.g.
                        data/manuscripts/vat.gr.1209/
        manuscript_id: Stable identifier for this manuscript.
        images_subdir: Subdirectory within manuscript_dir that holds images.
                       Defaults to 'images'.
    """

    def __init__(
        self,
        manuscript_dir: Path,
        manuscript_id: str,
        images_subdir: str = "images",
    ) -> None:
        self._manuscript_id = manuscript_id
        self._manuscript_dir = Path(manuscript_dir)
        self._images_dir = self._manuscript_dir / images_subdir
        self._manifest_path = self._manuscript_dir / "manifest.json"

    def get_manuscript_id(self) -> str:
        return self._manuscript_id

    def list_folios(self) -> list[str]:
        """Return folio IDs sorted by filename."""
        if not self._images_dir.exists():
            return []
        folios = [
            p.stem
            for p in sorted(self._images_dir.iterdir())
            if p.suffix.lower() in _IMAGE_EXTENSIONS
        ]
        return folios

    def get_folio_image(self, folio_id: str) -> Path:
        """Return the local path to the folio image."""
        for ext in _IMAGE_EXTENSIONS:
            candidate = self._images_dir / f"{folio_id}{ext}"
            if candidate.exists():
                return candidate
        raise FileNotFoundError(
            f"No image found for folio {folio_id!r} in {self._images_dir}"
        )

    def get_folio_metadata(self, folio_id: str) -> dict:
        """Return metadata for a folio, supplemented by manifest.json if present."""
        metadata: dict = {
            "folio_id": folio_id,
            "manuscript_id": self._manuscript_id,
            "image_source_url": None,
        }
        if self._manifest_path.exists():
            manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            for sequence in manifest.get("sequences", []):
                for canvas in sequence.get("canvases", []):
                    label = str(canvas.get("label", "")).strip()
                    if label == folio_id:
                        metadata["width"] = canvas.get("width")
                        metadata["height"] = canvas.get("height")
                        metadata["canvas_id"] = canvas.get("@id") or canvas.get("id")
                        break
        return metadata
