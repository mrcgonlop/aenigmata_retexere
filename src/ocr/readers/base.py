from abc import ABC, abstractmethod
from pathlib import Path


class ManuscriptReader(ABC):
    """Abstract interface for reading manuscript folio images from any source."""

    @abstractmethod
    def get_manuscript_id(self) -> str:
        """Return a stable identifier for this manuscript (e.g., 'vat.gr.1209')."""

    @abstractmethod
    def list_folios(self) -> list[str]:
        """Return an ordered list of folio identifiers (e.g., ['1r', '1v', '2r', ...])."""

    @abstractmethod
    def get_folio_image(self, folio_id: str) -> Path:
        """Return local path to the folio image, downloading/caching if necessary."""

    @abstractmethod
    def get_folio_metadata(self, folio_id: str) -> dict:
        """Return metadata for a folio: dimensions, image_source_url, scribal_hand, etc."""
