# aenigmata — Architecture

## System Overview

aenigmata is composed of three primary layers, each independently useful but designed to work together as a pipeline:

```
┌─────────────────────────────────────────────────────────┐
│                  Layer 3: Exploration UI                 │
│         Web app + PDF export — reader-facing             │
├─────────────────────────────────────────────────────────┤
│                Layer 2: Lexical Engine                   │
│    Semantic database — definitions, provenance, fields   │
├─────────────────────────────────────────────────────────┤
│              Layer 1: Text Acquisition                   │
│     OCR pipeline — manuscript images → annotated text    │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1: Text Acquisition Pipeline

### Purpose
Convert manuscript folio images into structured, annotated digital text with multi-hypothesis readings.

### Input
High-resolution folio images from digitized manuscripts (starting with Codex Vaticanus via the Vatican Digital Library).

### Processing Pipeline

```
Folio Image
    │
    ▼
┌──────────────┐
│ Preprocessing │  — Binarization, deskew, noise reduction
└──────┬───────┘
       ▼
┌──────────────┐
│  Line/Region  │  — Segment folio into text regions
│  Detection    │
└──────┬───────┘
       ▼
┌──────────────┐
│  OCR Engine   │  — Kraken with custom model trained on uncial script
│  (Kraken)     │  — Outputs N-best candidates with confidence scores
└──────┬───────┘
       ▼
┌──────────────┐
│ Post-process  │  — Word boundary detection (uncial has no spaces)
│ & Tokenize    │  — Normalize unicode representations
└──────┬───────┘
       ▼
Structured Output (JSON)
```

### Output Format

Each folio produces a JSON document:

```json
{
  "manuscript": "vat.gr.1209",
  "folio": "123r",
  "image_source": "https://digi.vatlib.it/...",
  "regions": [
    {
      "region_id": "r1",
      "bbox": [x1, y1, x2, y2],
      "lines": [
        {
          "line_id": "r1_l1",
          "bbox": [x1, y1, x2, y2],
          "tokens": [
            {
              "token_id": "r1_l1_t1",
              "bbox": [x1, y1, x2, y2],
              "candidates": [
                { "text": "ΕΝΑΡΧΗ", "confidence": 0.94 },
                { "text": "ΕΝΑΡΧΕΙ", "confidence": 0.03 },
                { "text": "ΕΝΑΡΧΑΙ", "confidence": 0.02 }
              ],
              "selected": 0
            }
          ]
        }
      ]
    }
  ]
}
```

### ManuscriptReader Interface

Manuscripts come from heterogeneous sources with different directory layouts, naming conventions, and access methods. A generic abstract interface decouples the OCR pipeline from any specific source:

```python
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
```

Concrete implementations live in `src/ocr/readers/`:

| Class | Source | Notes |
|---|---|---|
| `IIIFManuscriptReader` | Vatican Digital Library | Fetches via IIIF manifest URL |
| `BritishLibraryReader` | Codex Sinaiticus (BL) | Direct image download |
| `LocalManuscriptReader` | Local filesystem | For pre-downloaded or custom images |

Each reader handles its own directory structure and caching. The OCR pipeline only depends on `ManuscriptReader`, so new sources require only a new reader class.

### Key Design Decisions

- **Multi-hypothesis output**: The OCR never commits to a single reading. Downstream layers can use alternatives.
- **Coordinate preservation**: Every token maps back to its physical location on the folio for visual verification.
- **Manuscript-specific models**: Kraken allows training custom recognition models. The Vaticanus has distinct scribal hands (original scribe + later correctors) that require separate models or at minimum separate confidence calibration.
- **No normalization to modern editions**: The text is captured as it appears on the manuscript, not corrected against modern critical editions.
- **Source-agnostic pipeline**: The OCR pipeline operates on images delivered by a `ManuscriptReader` implementation; it has no knowledge of where images come from.

### Technologies
- **Kraken** — Primary OCR engine, designed for historical scripts
- **OpenCV / Pillow** — Image preprocessing
- **Custom training data** — Built from existing Vaticanus transcriptions (alignment tool needed)

---

## Layer 2: Lexical Engine

### Purpose
Provide comprehensive, period-aware semantic data for every Greek lemma, with full provenance and explicit source attribution.

### Database Schema (SQLite)

```sql
-- Core lemma table
CREATE TABLE lemmas (
    id INTEGER PRIMARY KEY,
    lemma TEXT NOT NULL,          -- dictionary form (e.g., λόγος)
    transliteration TEXT,         -- ASCII transliteration
    pos TEXT,                     -- part of speech
    morphology_json TEXT          -- full morphological paradigm
);

-- Sources (lexicons, dictionaries, corpora)
-- Declared before definitions/attestations because they reference it.
-- New sources are added by registering here + writing an ingest/ script.
-- type: 'lexicon' | 'corpus' | 'derived'
CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- e.g., "Perseus Middle Liddell"
    type TEXT NOT NULL,           -- 'lexicon', 'corpus', 'derived'
    date TEXT,                    -- when the source was created
    tradition TEXT,               -- interpretive tradition if any
    url TEXT,                     -- where to find it
    license TEXT NOT NULL,        -- licensing information (required for open-source hygiene)
    bias_notes TEXT               -- known biases or limitations
);

-- Definitions from specific sources
-- source_id and lemma_id are mandatory — no orphaned definitions allowed.
-- confidence: 0.0000–1.0000, representing how well-attested this meaning is
--   across the corpus (normalized frequency/coverage metric, not OCR probability).
CREATE TABLE definitions (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    definition TEXT NOT NULL,     -- the definition text
    period_start INTEGER,         -- century (negative = BCE, e.g., -5 = 5th century BCE)
    period_end INTEGER,           -- century (negative = BCE, e.g., 5 = 5th century CE)
    tradition TEXT,               -- 'secular', 'christian', 'jewish', 'philosophical', etc.
    original_language TEXT,       -- language the definition is written in
    confidence REAL               -- 0.0000–1.0000: attestation strength across corpus
);

-- Usage attestations from actual texts
-- source_id and lemma_id are mandatory.
CREATE TABLE attestations (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    work TEXT NOT NULL,           -- e.g., "Plato, Republic 509b"
    author TEXT,
    date_approx INTEGER,          -- approximate century (negative = BCE)
    tradition TEXT,               -- secular, christian, etc.
    context TEXT,                 -- surrounding text for context
    translation TEXT,             -- how it's used in this specific passage
    source_id INTEGER NOT NULL REFERENCES sources(id)
);

-- Semantic field mappings
CREATE TABLE semantic_fields (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    field_name TEXT NOT NULL,     -- e.g., "speech/discourse", "reason/rationality"
    modern_equivalents TEXT,      -- JSON array of modern-language approximations
    notes TEXT                    -- what's lost or gained in each mapping
);

-- Cross-references between lemmas
CREATE TABLE cross_references (
    id INTEGER PRIMARY KEY,
    from_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    to_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    relationship TEXT,            -- 'synonym', 'antonym', 'semantic_field', 'derived', etc.
    notes TEXT
);

-- Semantic drift detection
-- secular_definition_id and christian_definition_id point to representative
-- definitions in the definitions table — no text is duplicated here.
-- evidence: JSON array of definition IDs used in the divergence computation.
-- divergence_score: 0.0000–1.0000 (e.g., cosine distance between embedding centroids)
CREATE TABLE drift_flags (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    secular_definition_id INTEGER REFERENCES definitions(id),   -- representative secular def
    christian_definition_id INTEGER REFERENCES definitions(id), -- representative christian def
    divergence_score REAL,        -- 0.0000–1.0000 computed divergence metric
    evidence TEXT,                -- JSON array of definition IDs used in comparison
    notes TEXT
);

-- Manuscript-specific: links OCR tokens to lemmas
-- confidence: 0.0000–1.0000, probability that the morphological parse and
--   lemma assignment are correct (may reflect multiple competing parses).
CREATE TABLE token_lemma_links (
    id INTEGER PRIMARY KEY,
    manuscript TEXT NOT NULL,
    folio TEXT NOT NULL,
    token_id TEXT NOT NULL,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    morphological_form TEXT,      -- specific form in text (e.g., λόγον = acc.sg.)
    parse TEXT,                   -- full morphological parse
    confidence REAL               -- 0.0000–1.0000: parse/lemma assignment confidence
);
```

### Data Ingestion Pipeline

```
┌─────────────────┐   ┌─────────────────┐   ┌──────────────────┐
│ Perseus Digital  │   │   Wiktionary    │   │    Logeion       │
│ Library (open)   │   │ Ancient Greek   │   │  (UChicago)      │
└────────┬────────┘   └────────┬────────┘   └────────┬─────────┘
         │                     │                      │
         ▼                     ▼                      ▼
    ┌─────────────────────────────────────────────────────┐
    │              Ingestion & Normalization               │
    │  — Lemma unification (handle variant spellings)      │
    │  — Source tagging (every fact gets provenance)        │
    │  — Period dating (when was this meaning attested?)    │
    │  — Tradition labeling (secular vs. religious context) │
    └──────────────────────┬──────────────────────────────┘
                           ▼
                    ┌──────────────┐
                    │   SQLite DB   │
                    └──────────────┘
```

### Derived Data Generation

Beyond ingesting existing lexicons, the engine generates its own data:

1. **Frequency analysis**: How often each lemma appears in secular vs. religious corpora per century
2. **Semantic drift detection**: Word2Vec or similar embeddings trained separately on secular and Christian texts, then compared — large vector distances flag words whose meaning shifted
3. **Collocation analysis**: What words appear near each lemma in different traditions
4. **LXX translation mapping**: For Septuagint words, record which Hebrew/Aramaic term they render, treating this as a data point about translator choice rather than word meaning

### Adding New Sources

The ingestion architecture is intentionally open and modular. Each source is an independent Python module that follows the same pattern:

1. **Register** a row in the `sources` table (name, type, license, bias_notes).
2. **Write** an ingestion script in `src/lexicon/ingest/<source_name>.py` that reads from the external resource and inserts into `lemmas`, `definitions`, and `attestations` using the registered `source_id`.
3. **Tag every row** with that `source_id` — the schema enforces this via `NOT NULL`.
4. **Deduplicate** against existing lemmas using the shared lemma unification utilities.
5. **Test** in `tests/test_lexicon.py` — a test that verifies the ingest produces valid, non-orphaned data.

No changes to core code are required to add a new source. The `sources.type` field classifies the provenance:

| type | meaning |
|---|---|
| `lexicon` | Traditional Greek–English lexicon (e.g., LSJ, Middle Liddell) |
| `corpus` | Raw text corpus used for frequency/collocation analysis |
| `derived` | Computationally generated data (e.g., Word2Vec drift scores) |

### Key Design Decisions

- **SQLite, not a graph database**: Simpler to deploy, fork, and contribute to. The relational model is sufficient and keeps the barrier to entry low. The entire lexical database ships as a single file.
- **Provenance is mandatory**: No definition exists without a source. This is architectural, not aspirational — `source_id NOT NULL` is enforced at the schema level.
- **Tradition labeling**: Every definition and attestation is tagged with its interpretive tradition so readers can filter and compare.
- **No privileged source**: The engine doesn't rank dictionaries. It presents what each source says and lets the reader weigh them.
- **Open ingestion**: Adding a new lexical source requires only a new script and a `sources` row — no changes to core code.

### Technologies
- **SQLite** — Database
- **CLTK** — Morphological analysis and lemmatization
- **Morpheus (Perseus)** — Greek morphological parser
- **Python scrapers** — For ingesting open web resources
- **Gensim / scikit-learn** — For distributional semantics and drift detection

---

## Layer 3: Exploration Interface

### Purpose
A web application (with PDF export) that lets readers navigate ancient Greek texts interactively, with every word serving as an entry point into its full semantic profile.

### Architecture

```
┌─────────────────────────────────────────────┐
│              React Frontend                  │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │  Text View   │  │  Semantic Panel      │  │
│  │              │  │                      │  │
│  │  ΕΝΑΡΧΗΗΝ   │──│  λόγος               │  │
│  │  ΟΛΟΓΟΣ     │  │  ─────               │  │
│  │  ΚΑΙΟΛΟΓΟΣ  │  │  Attested meanings:  │  │
│  │  ΗΝΠΡΟΣΤΟΝ  │  │  • reason (Plato)    │  │
│  │  ΘΕΟΝ       │  │  • account (Herod.)  │  │
│  │              │  │  • discourse (Arist.)│  │
│  │  [words are  │  │  • ratio (Euclid)   │  │
│  │   clickable] │  │  • principle (Stoic) │  │
│  │              │  │                      │  │
│  │              │  │  Semantic drift: ⚠   │  │
│  │              │  │  Christian usage     │  │
│  │              │  │  diverges from       │  │
│  │              │  │  secular baseline    │  │
│  └─────────────┘  └──────────────────────┘  │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │  Manuscript View (folio image)        │   │
│  │  — highlights word location on scan   │   │
│  └──────────────────────────────────────┘   │
└──────────────────┬──────────────────────────┘
                   │ API calls (JSON over HTTP)
                   ▼
┌──────────────────────────────────────────────┐
│              Backend API (Python/FastAPI)      │
│  — Serves text, lexical data, folio metadata  │
│  — Queries SQLite lexical database            │
│  — Handles morphological lookups              │
│  — PDF export generation                      │
└──────────────────────────────────────────────┘
```

### Frontend Components

**Text View Panel**
- Displays Greek text with word-level interactivity
- Color coding for OCR confidence (high confidence = normal, low = highlighted)
- Click any word to open its semantic profile
- Toggle between: manuscript diplomatic transcription / normalized text / interlinear with morphological parse
- Manuscript/folio navigation

**Semantic Panel**
- Full lexical entry assembled from all sources
- Definitions grouped by source with provenance badges
- Usage attestations with date and tradition labels
- Semantic field visualization (cluster diagram or similar)
- Drift flag when Christian/secular meanings diverge
- Links to the folio image location for the word

**Manuscript View**
- IIIF image viewer showing the actual folio scan
- Highlights the bounding box of the currently selected word
- Navigation between folios

**Comparison View**
- Side-by-side comparison of how different traditions define the same word
- Timeline view showing how a word's dominant meaning shifted over centuries

### PDF Export

For offline study, the system exports annotated PDFs:
- Greek text with interlinear morphological parse
- Footnotes for each word containing top definitions from period sources
- Margin notes for semantic drift flags
- Appendix with full lexical entries for all words in the exported section
- Generated via WeasyPrint from the same data the web UI uses

### Technologies
- **React + TypeScript** — Frontend
- **FastAPI (Python)** — Backend API
- **SQLite** — Lexical database (served directly, no ORM overhead needed)
- **OpenSeadragon or Mirador** — IIIF manuscript image viewer
- **WeasyPrint** — PDF generation
- **Vite** — Frontend build

---

## Data Flow Summary

```
Vatican Digital Library (IIIF images)
        │
        ▼
  OCR Pipeline (Kraken)
        │
        ▼
  Structured Text (JSON)  ◄──── stored in /data/manuscripts/
        │
        ▼
  Morphological Analysis (CLTK/Morpheus)
        │
        ▼
  Token-Lemma Linking ────────► SQLite Lexical DB ◄──── Ingested from:
        │                              │                  - Perseus
        │                              │                  - Wiktionary
        │                              │                  - Logeion
        │                              │                  - Corpus analysis
        ▼                              ▼
  FastAPI Backend ─────────────► React Frontend
        │
        ▼
  PDF Export (WeasyPrint)
```

---

## Directory Structure

```
aenigmata/
├── README.md
├── ARCHITECTURE.md
├── TODO.md
├── CLAUDE.md                    # Claude Code agent instructions
├── pyproject.toml               # Python project config
├── package.json                 # Frontend dependencies
│
├── src/
│   ├── ocr/                     # Layer 1: Text Acquisition
│   │   ├── readers/             # ManuscriptReader implementations
│   │   │   ├── base.py          # Abstract ManuscriptReader interface
│   │   │   ├── iiif.py          # IIIFManuscriptReader (Vatican Digital Library)
│   │   │   ├── british_library.py # BritishLibraryReader (Codex Sinaiticus)
│   │   │   └── local.py         # LocalManuscriptReader (pre-downloaded images)
│   │   ├── preprocess.py        # Image preprocessing
│   │   ├── segment.py           # Region/line detection
│   │   ├── recognize.py         # OCR with multi-hypothesis output
│   │   ├── tokenize.py          # Word boundary detection
│   │   └── models/              # Trained Kraken models
│   │
│   ├── lexicon/                 # Layer 2: Lexical Engine
│   │   ├── db.py                # Database access layer
│   │   ├── schema.sql           # Database schema
│   │   ├── ingest/              # Data ingestion scripts
│   │   │   ├── perseus.py       # Perseus Digital Library scraper
│   │   │   ├── wiktionary.py    # Wiktionary Ancient Greek scraper
│   │   │   ├── logeion.py       # Logeion aggregator
│   │   │   └── corpus.py        # Corpus-derived frequency/collocation data
│   │   ├── morphology.py        # CLTK/Morpheus integration
│   │   ├── drift.py             # Semantic drift detection
│   │   └── linker.py            # Token-to-lemma linking
│   │
│   ├── api/                     # Backend API
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── text.py          # Text/manuscript endpoints
│   │   │   ├── lexicon.py       # Lexical lookup endpoints
│   │   │   └── export.py        # PDF export endpoint
│   │   └── pdf_generator.py     # PDF generation
│   │
│   └── frontend/                # Layer 3: Exploration UI
│       ├── src/
│       │   ├── components/
│       │   │   ├── TextView.tsx
│       │   │   ├── SemanticPanel.tsx
│       │   │   ├── ManuscriptView.tsx
│       │   │   └── ComparisonView.tsx
│       │   ├── App.tsx
│       │   └── main.tsx
│       ├── index.html
│       └── vite.config.ts
│
├── data/
│   ├── manuscripts/             # OCR output JSON files
│   ├── lexicon.db               # SQLite lexical database
│   └── models/                  # Trained OCR models
│
├── scripts/
│   ├── setup.sh                 # Environment setup
│   ├── ingest_all.py            # Run all ingestion pipelines
│   └── train_ocr.py             # OCR model training script
│
└── tests/
    ├── test_ocr.py
    ├── test_lexicon.py
    └── test_api.py
```

---

## Deployment

The tool is designed to be **self-hostable with zero infrastructure cost**:

- SQLite database = single file, no database server
- Static frontend build served by the same Python process
- Can run entirely on a laptop for personal study
- Can be deployed to a cheap VPS or free-tier cloud service for public access
- The entire data directory (manuscripts + lexicon DB) can be distributed as a downloadable archive

---

## Future Considerations

- **Collaborative annotation**: Allow scholars to contribute definitions and corrections
- **Additional manuscripts**: Codex Sinaiticus, papyri, Dead Sea Scrolls Greek fragments
- **Hebrew/Aramaic layer**: For LXX analysis, linking Greek back to source languages
- **LLM-assisted translation suggestions**: Using language models constrained by the period lexicon as a suggestion engine, not an authority
- **Coptic and Syriac**: Early translation traditions that preserve independent witness to meaning
- **API for external tools**: Let other digital humanities projects query the lexical engine
