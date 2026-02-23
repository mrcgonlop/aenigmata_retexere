# CLAUDE.md — Agent Instructions for Aglōssa

## Project Overview

Aglōssa is a tool for digitizing ancient Greek manuscripts and exploring their meaning through period-accurate lexical data, free from accumulated theological bias. Read README.md for the mission and ARCHITECTURE.md for technical design.

## Core Principle

**Every design decision serves deintermediation.** The goal is direct contact with original meaning. When in doubt, prefer transparency (show the data and its source) over authority (pick one answer). Never privilege one interpretive tradition over another.

## Repository Structure

```
aglossa/
├── src/
│   ├── ocr/          # Layer 1: Manuscript OCR pipeline (Python)
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

## Development Commands

```bash
# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

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

3. **Provenance is mandatory** — No lexical data enters the database without a source attribution. The schema enforces this via foreign keys.

4. **No privileged translation** — The UI never shows "the translation" — it shows definitions from multiple sources and lets the reader decide. When generating exports, present multiple options, not one.

5. **Tradition labeling** — Every definition and attestation carries a tradition tag (secular, christian, jewish, philosophical, etc.). This enables filtering and comparison.

## Working with the Lexical Database

The lexical database (SQLite) is the heart of the project. Key tables:

- `lemmas` — Dictionary forms of Greek words
- `definitions` — Definitions with source provenance and tradition tags
- `sources` — Where data comes from (lexicons, corpora, derived analysis)
- `attestations` — Actual usage examples from dated texts
- `semantic_fields` — Clusters of modern-language equivalents
- `drift_flags` — Words where Christian/secular meaning diverges

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
1. Research the source's terms of use
2. Write ingestion script in `src/lexicon/ingest/`
3. Add source metadata to `sources` table (including bias_notes)
4. Run ingestion and verify with `pytest tests/test_lexicon.py`

### Processing a new manuscript section
1. Download folio images to `data/manuscripts/{manuscript_id}/images/`
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
