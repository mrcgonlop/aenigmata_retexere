# data/manuscripts/

Manuscript data lives here. Raw folio images are **gitignored** (too large).
Download them with the provided scripts before running the OCR pipeline.

## Codex Vaticanus (vat.gr.1209)

```bash
# Download all folios at full resolution (~1 GB+, takes a while)
python scripts/download_vaticanus.py

# Download a subset for development (first 10 folios, 2000px wide)
python scripts/download_vaticanus.py --folios 10 --size "2000,"

# See what would be downloaded without fetching images
python scripts/download_vaticanus.py --dry-run
```

Images land in `data/manuscripts/vat.gr.1209/images/`.
The IIIF manifest (small JSON metadata) is committed at
`data/manuscripts/vat.gr.1209/manifest.json` once first fetched.

## Directory layout per manuscript

```
data/manuscripts/
└── <manuscript_id>/
    ├── manifest.json        ← IIIF manifest (committed)
    ├── images/              ← folio scans (gitignored)
    │   ├── 1r.jpg
    │   ├── 1v.jpg
    │   └── ...
    └── ocr/                 ← OCR output JSON (committed once generated)
        ├── 1r.json
        └── ...
```
