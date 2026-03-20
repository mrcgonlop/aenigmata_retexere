from src.ocr.readers.base import ManuscriptReader
from src.ocr.readers.iiif import IIIFManuscriptReader, vaticanus_reader
from src.ocr.readers.local import LocalManuscriptReader

__all__ = [
    "ManuscriptReader",
    "IIIFManuscriptReader",
    "LocalManuscriptReader",
    "vaticanus_reader",
]
