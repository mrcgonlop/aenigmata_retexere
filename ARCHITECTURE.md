# Architecture — Aglōssa

## System Overview

Aglōssa is composed of three primary layers, each independently useful but designed to work together as a pipeline:

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

### Key Design Decisions

- **Multi-hypothesis output**: The OCR never commits to a single reading. Downstream layers can use alternatives.
- **Coordinate preservation**: Every token maps back to its physical location on the folio for visual verification.
- **Manuscript-specific models**: Kraken allows training custom recognition models. The Vaticanus has distinct scribal hands (original scribe + later correctors) that require separate models or at minimum separate confidence calibration.
- **No normalization to modern editions**: The text is captured as it appears on the manuscript, not corrected against modern critical editions.

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

-- Definitions from specific sources
CREATE TABLE definitions (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER REFERENCES lemmas(id),
    source_id INTEGER REFERENCES sources(id),
    definition TEXT NOT NULL,     -- the definition text
    period_start INTEGER,         -- century (e.g., -5 for 5th century BCE)
    period_end INTEGER,
    tradition TEXT,               -- 'secular', 'christian', 'jewish', 'philosophical', etc.
    original_language TEXT,       -- language the definition is written in
    confidence REAL               -- how well-attested this meaning is
);

-- Sources (lexicons, dictionaries, corpora)
CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- e.g., "Perseus Middle Liddell"
    type TEXT,                    -- 'lexicon', 'corpus', 'derived'
    date TEXT,                    -- when the source was created
    tradition TEXT,               -- interpretive tradition if any
    url TEXT,                     -- where to find it
    license TEXT,                 -- licensing information
    bias_notes TEXT               -- known biases or limitations
);

-- Usage attestations from actual texts
CREATE TABLE attestations (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER REFERENCES lemmas(id),
    work TEXT NOT NULL,           -- e.g., "Plato, Republic 509b"
    author TEXT,
    date_approx INTEGER,         -- approximate century
    tradition TEXT,               -- secular, christian, etc.
    context TEXT,                 -- surrounding text for context
    translation TEXT,             -- how it's used in this specific passage
    source_id INTEGER REFERENCES sources(id)
);

-- Semantic field mappings
CREATE TABLE semantic_fields (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER REFERENCES lemmas(id),
    field_name TEXT,              -- e.g., "speech/discourse", "reason/rationality"
    modern_equivalents TEXT,      -- JSON array of modern-language approximations
    notes TEXT                    -- what's lost or gained in each mapping
);

-- Cross-references between lemmas
CREATE TABLE cross_references (
    id INTEGER PRIMARY KEY,
    from_lemma_id INTEGER REFERENCES lemmas(id),
    to_lemma_id INTEGER REFERENCES lemmas(id),
    relationship TEXT,            -- 'synonym', 'antonym', 'semantic_field', 'derived', etc.
    notes TEXT
);

-- Semantic drift detection
CREATE TABLE drift_flags (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER REFERENCES lemmas(id),
    secular_meaning TEXT,
    christian_meaning TEXT,
    divergence_score REAL,        -- computed metric
    evidence TEXT,                -- JSON with supporting data
    notes TEXT
);

-- Manuscript-specific: links OCR tokens to lemmas
CREATE TABLE token_lemma_links (
    id INTEGER PRIMARY KEY,
    manuscript TEXT,
    folio TEXT,
    token_id TEXT,
    lemma_id INTEGER REFERENCES lemmas(id),
    morphological_form TEXT,      -- specific form in text (e.g., λόγον = acc.sg.)
    parse TEXT                    -- full morphological parse
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

### Key Design Decisions

- **SQLite, not a graph database**: Simpler to deploy, fork, and contribute to. The relational model is sufficient and keeps the barrier to entry low. The entire lexical database ships as a single file.
- **Provenance is mandatory**: No definition exists without a source. This is architectural, not aspirational — the schema enforces it.
- **Tradition labeling**: Every definition and attestation is tagged with its interpretive tradition so readers can filter and compare.
- **No privileged source**: The engine doesn't rank dictionaries. It presents what each source says and lets the reader weigh them.

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
- Generated via WeasyPrint or ReportLab from the same data the web UI uses

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
aglossa/
├── README.md
├── ARCHITECTURE.md
├── TODO.md
├── CLAUDE.md                    # Claude Code agent instructions
├── pyproject.toml               # Python project config
├── package.json                 # Frontend dependencies
│
├── src/
│   ├── ocr/                     # Layer 1: Text Acquisition
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
