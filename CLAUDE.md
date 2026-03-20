# CLAUDE.md — Agent Instructions

## Project Overview

**aenigmata** is a tool for digitizing ancient Greek manuscripts and exploring their meaning through period-accurate lexical data (5th century BCE – 5th century CE), free from accumulated theological bias. Read README.md for the mission and ARCHITECTURE.md for technical design.

## Core Principle

**Every design decision serves deintermediation.** The goal is direct contact with original meaning. When in doubt, prefer transparency (show the data and its source) over authority (pick one answer). Never privilege one interpretive tradition over another.

## Repository Structure

```
aenigmata/
├── src/
│   ├── ocr/          # Layer 1: Manuscript OCR pipeline (Python) — includes readers/ for ManuscriptReader implementations
│   ├── lexicon/      # Layer 2: Lexical engine + data ingestion (Python)
│   ├── api/          # Backend API — FastAPI (Python)
│   └── frontend/     # Layer 3: React + TypeScript UI
├── data/
│   ├── manuscripts/  # OCR output JSON
│   └── lexicon.db    # SQLite lexical database
├── scripts/          # Setup and utility scripts
└── tests/            # Test suite
```

## Tech Stack

- **Python 3.11+** — OCR, NLP, API, data ingestion
- **TypeScript + React** — Frontend (Vite build)
- **SQLite** — Lexical database (single file, no server)
- **FastAPI** — Backend API
- **Kraken** — Historical manuscript OCR
- **CLTK** — Classical language NLP toolkit
- **WeasyPrint** — PDF generation

## Runtime Environment

**OS**: Windows 10, running inside VS Code with the Claude Code extension.

**Python**: Managed via **Anaconda**. The active environment is `aenigmata` (Python 3.11).
Always run Python commands through this environment. Do NOT use `python` or `pip` directly —
use `conda run -n aenigmata <command>` from the shell, or activate the environment first.

```bash
# Activate the environment (do this once per terminal session)
conda activate aenigmata

# Or run a single command without activating:
conda run -n aenigmata python -m src.lexicon.db --init
```

**conda PATH** (needed when running from Claude Code's bash shell, where conda is not on PATH):
```bash
export PATH="/c/Users/mrcgo/anaconda3/Scripts:/c/Users/mrcgo/anaconda3:/c/Users/mrcgo/anaconda3/condabin:$PATH"
```

**Encoding**: Windows console defaults to cp1252, which cannot encode Greek text.
`PYTHONIOENCODING=utf-8` is set as a permanent conda env var in `aenigmata`.
If Greek output still fails via `conda run`, prefix with `PYTHONIOENCODING=utf-8`.

**Key installed versions** (as of 2026-03-10):
- Kraken 6.0.3 — API differs from docs written for 5.x (see notes in `src/ocr/recognize.py`)
- PyTorch 2.9.0+cpu — CPU-only build; reinstalled to fix `shm.dll` DLL error on Windows
- numpy 2.0.2 — pinned to match `kraken~=2.0.0` requirement

**Kraken 6.x API notes** (important — the public docs describe 5.x):
- `rpred` is at `kraken.rpred`, NOT `kraken.lib.rpred`
- `blla.py` is a plain module file; calling `blla.segment()` without a model arg fails with
  `'kraken.blla' is not a package` because it uses `importlib.resources.files('kraken.blla')`.
  Workaround: load `blla.mlmodel` explicitly via `TorchVGSLModel.load_model()` and pass it in.
- Segmentation models need `vgsl.TorchVGSLModel.load_model()`, not `models.load_any()`.
- All current models (`catlips`, `savile`) have `seg_type='bbox'` — they use **legacy bbox
  segmentation** (`kraken.pageseg`), not BLLA. Using BLLA with these causes degraded output.
- **bbox segmentation fix**: `pageseg.segment()` requires an `nlbin`-binarized `'L'`-mode image
  (NOT `.convert('1')`). With `'L'` input, pageseg returns a proper `Segmentation` object.
  With a `'1'` input, pageseg returns a legacy dict that `rpred` cannot accept.
- **pageseg scale parameter**: default `scale=None` finds hundreds of tiny character boxes.
  Use `scale=30` for manuscript images (~2000–3000px wide) to get proper text line detection
  (~85 lines per folio vs. 341 character-level boxes at default scale).
- `pageseg.segment()` issues a "Too many connected components" warning for noisy binary images;
  with proper `nlbin` binarization this warning appears but doesn't affect results.

**Kraken models** (in `data/models/`, all are `seg_type=bbox`):
- `model_grc_catlips.mlmodel` — primary model; tested and working with `scale=30`
- `model_grc_catlips-nfc.mlmodel` / `model_grc_catlips-nfd.mlmodel` — NFC/NFD Unicode variants
- `model_grc_catlips1.mlmodel` / `model_grc_catlips2.mlmodel` — training iterations
- `model_grc_savile.mlmodel` — different corpus; untested

## Development Commands

```bash
# Python environment — always use the aenigmata conda environment
conda activate aenigmata
pip install -e ".[dev]"   # if adding new deps; run inside activated env

# Run API server
uvicorn src.api.main:app --reload --port 8000

# Run frontend dev server
cd src/frontend && npm install && npm run dev

# Run tests
pytest tests/

# Initialize/reset the lexical database
python -m src.lexicon.db --init

# Run a specific ingestion pipeline
python -m src.lexicon.ingest.perseus
python -m src.lexicon.ingest.wiktionary

# Process a manuscript folio
python -m src.ocr.recognize --manuscript vat.gr.1209 --folio 123r
```

## Code Conventions

### Python
- Use type hints everywhere
- Docstrings on all public functions (Google style)
- f-strings for formatting
- `pathlib.Path` for all file paths
- dataclasses or Pydantic models for structured data
- No bare `except:` — always catch specific exceptions

### TypeScript/React
- Functional components with hooks
- Props interfaces defined explicitly
- Tailwind for styling (no CSS modules)
- Avoid `any` type — use proper typing

### Database
- All SQL queries use parameterized statements (never string interpolation)
- Every definition/attestation MUST have a source_id — this is non-negotiable
- Use transactions for batch inserts during ingestion

### Git
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- One logical change per commit
- Always run tests before committing

## Key Technical Decisions (Do Not Change Without Discussion)

1. **SQLite over PostgreSQL/Neo4j** — Portability and zero-infrastructure deployment are requirements. The entire project must be forkable and runnable on a laptop.

2. **Multi-hypothesis OCR output** — The OCR pipeline MUST output ranked candidates with confidence scores. Never collapse to a single reading.

3. **Provenance is mandatory** — No lexical data enters the database without a source attribution. The schema enforces this via `NOT NULL` foreign keys on `source_id` and `lemma_id` in `definitions`, `attestations`, and related tables.

4. **No privileged translation** — The UI never shows "the translation" — it shows definitions from multiple sources and lets the reader decide. When generating exports, present multiple options, not one.

5. **Tradition labeling** — Every definition and attestation carries a tradition tag (secular, christian, jewish, philosophical, etc.). This enables filtering and comparison.

## Working with the Lexical Database

The lexical database (SQLite) is the heart of the project. Key tables:

- `lemmas` — Dictionary forms of Greek words
- `definitions` — Definitions with source provenance and tradition tags
- `sources` — Where data comes from (lexicons, corpora, derived analysis)
- `attestations` — Actual usage examples from dated texts
- `semantic_fields` — Clusters of modern-language equivalents
- `drift_flags` — Words where Christian/secular meaning diverges (references `definitions.id`, no text duplication)

See ARCHITECTURE.md for the full schema.

When adding new data sources:
1. Create a new ingestion script in `src/lexicon/ingest/`
2. Register the source in the `sources` table with honest `bias_notes`
3. Tag every inserted definition with the source_id
4. Run deduplication against existing lemmas
5. Add a test that verifies the ingestion produces valid data

## Working with the OCR Pipeline

The OCR pipeline processes manuscript folio images into structured JSON. The output format is defined in ARCHITECTURE.md.

Key considerations:
- The Codex Vaticanus uses **uncial script** (continuous majuscule with no word separation)
- Word boundary detection is a separate step from character recognition
- Multiple scribal hands exist (original scribe + correctors) — note which hand in metadata
- Always preserve bounding box coordinates for visual verification

## Working with the Frontend

The frontend is a React SPA that communicates with the FastAPI backend via JSON API.

Core components:
- `TextView` — Displays Greek text with clickable words
- `SemanticPanel` — Shows full lexical entry for selected word
- `ManuscriptView` — IIIF image viewer with word highlighting
- `ComparisonView` — Side-by-side tradition comparison

Design principles:
- Information density is good — scholars want to see data
- But progressive disclosure — don't overwhelm on first click
- Every piece of data shown must be traceable to its source
- Works without JavaScript for basic text display (progressive enhancement)

## Common Tasks

### Adding a new lexical source
The ingestion system is open and modular — no core code changes required.
1. Research the source's terms of use
2. Register source in `sources` table (name, type, license, bias_notes)
3. Write ingestion script in `src/lexicon/ingest/<source_name>.py` — every inserted row must carry the registered `source_id`
4. Run deduplication against existing lemmas using shared utilities
5. Verify with `pytest tests/test_lexicon.py` (test must confirm no orphaned definitions)

### Adding a new manuscript source
1. Write a `ManuscriptReader` subclass in `src/ocr/readers/`
2. Implement `get_manuscript_id()`, `list_folios()`, `get_folio_image()`, `get_folio_metadata()`
3. Pass the reader instance to the OCR pipeline — no other changes required

### Processing a new manuscript section
1. Instantiate the appropriate `ManuscriptReader` for the source
2. Run OCR: `python -m src.ocr.recognize --manuscript {id} --folio {folio}`
3. Review output in `data/manuscripts/{manuscript_id}/ocr/`
4. Run token-lemma linking: `python -m src.lexicon.linker --manuscript {id} --folio {folio}`

### Adding a new API endpoint
1. Add route in appropriate file under `src/api/routes/`
2. Add corresponding test in `tests/test_api.py`
3. Update frontend to consume the new endpoint

## External Resources

- Perseus Digital Library: http://www.perseus.tufts.edu/
- CLTK documentation: https://docs.cltk.org/
- Kraken documentation: https://kraken.re/
- Vatican Digital Library IIIF: https://digi.vatlib.it/
- Logeion: https://logeion.uchicago.edu/
- SWORD modules: https://crosswire.org/sword/modules/
