# TODO — Aglōssa Roadmap

## Milestone 0: Project Foundation
- [ ] Initialize repository structure (directories, configs)
- [ ] Set up Python project with pyproject.toml (dependencies: cltk, kraken, fastapi, requests, beautifulsoup4, gensim)
- [ ] Set up frontend project with Vite + React + TypeScript
- [ ] Create SQLite schema and initialization script
- [ ] Write CONTRIBUTING.md with guidelines for contributors
- [ ] Set up basic CI (linting, tests)

## Milestone 1: Lexical Engine — Data Ingestion
*Goal: Build a usable lexical database from freely available sources.*

- [ ] **Perseus Digital Library ingestion**
  - [ ] Scrape/parse Middle Liddell Greek-English Lexicon entries
  - [ ] Extract lemmas, definitions, and citations
  - [ ] Map to standardized lemma forms
  - [ ] Tag all entries with source provenance

- [ ] **Wiktionary Ancient Greek ingestion**
  - [ ] Parse Wiktionary Ancient Greek entries via API or dump
  - [ ] Extract definitions, etymologies, usage notes
  - [ ] Normalize lemma forms to match Perseus data
  - [ ] Handle multiple senses and cross-references

- [ ] **Logeion integration**
  - [ ] Investigate Logeion API or scraping feasibility
  - [ ] Extract definitions from available dictionaries
  - [ ] Respect terms of use — document access method

- [ ] **Morphological engine setup**
  - [ ] Integrate CLTK for Ancient Greek lemmatization
  - [ ] Set up Morpheus (Perseus) as fallback parser
  - [ ] Build form → lemma lookup that handles Koine-specific forms
  - [ ] Test against known Septuagint/NT vocabulary

- [ ] **Database population**
  - [ ] Run all ingestion pipelines
  - [ ] Deduplicate and merge lemma entries across sources
  - [ ] Validate data integrity (every definition has a source)
  - [ ] Generate basic statistics (lemma count, definition coverage)

## Milestone 2: Text Acquisition — First Manuscript
*Goal: Digitize a section of the Codex Vaticanus with multi-hypothesis OCR.*

- [ ] **Image acquisition**
  - [ ] Script to download Vaticanus folio images from Vatican Digital Library IIIF endpoint
  - [ ] Organize by folio number with metadata
  - [ ] Verify image quality and resolution

- [ ] **OCR pipeline — preprocessing**
  - [ ] Implement binarization for parchment manuscripts
  - [ ] Implement deskew correction
  - [ ] Implement region/line segmentation for continuous uncial script

- [ ] **OCR pipeline — recognition**
  - [ ] Evaluate Kraken with existing Greek models
  - [ ] If insufficient: prepare training data from existing Vaticanus transcriptions
  - [ ] Train custom Kraken model on Vaticanus uncial hand
  - [ ] Implement N-best output with confidence scores

- [ ] **OCR pipeline — post-processing**
  - [ ] Word boundary detection (uncial manuscripts lack word separation)
  - [ ] Unicode normalization for polytonic Greek
  - [ ] JSON output in the defined structured format
  - [ ] Coordinate mapping (token → bounding box on folio)

- [ ] **Token-lemma linking**
  - [ ] For each OCR token, run morphological analysis
  - [ ] Link to lemma entries in the lexical database
  - [ ] Handle ambiguous parses (store all possibilities with confidence)

- [ ] **Initial target**: John 1:1–18 (the Prologue)
  - [ ] Process relevant folios
  - [ ] Verify OCR output against known transcriptions
  - [ ] Complete token-lemma linking for all words

## Milestone 3: Exploration Interface — MVP
*Goal: A working web UI for exploring the digitized text with lexical data.*

- [ ] **Backend API (FastAPI)**
  - [ ] `/api/manuscripts` — list available manuscripts
  - [ ] `/api/manuscripts/{id}/folios` — list folios
  - [ ] `/api/manuscripts/{id}/folios/{folio}/text` — get structured text
  - [ ] `/api/lexicon/{lemma}` — get full lexical entry
  - [ ] `/api/lexicon/{lemma}/definitions` — definitions with filters (source, tradition, period)
  - [ ] `/api/morphology/{form}` — parse a Greek form

- [ ] **Frontend — Text View**
  - [ ] Display Greek text with word-level click targets
  - [ ] Color-code words by OCR confidence
  - [ ] Show OCR alternatives on hover/click
  - [ ] Folio navigation

- [ ] **Frontend — Semantic Panel**
  - [ ] Display full lexical entry for selected word
  - [ ] Group definitions by source with provenance badges
  - [ ] Show usage attestations with date and tradition
  - [ ] Morphological parse display

- [ ] **Frontend — Manuscript View**
  - [ ] Embed IIIF image viewer (OpenSeadragon)
  - [ ] Highlight selected word's bounding box on folio image
  - [ ] Synchronized navigation with text view

- [ ] **PDF Export**
  - [ ] Generate annotated PDF for a selected text range
  - [ ] Interlinear format with morphological parse
  - [ ] Footnotes with top definitions per word
  - [ ] Basic styling and readability

## Milestone 4: Semantic Analysis
*Goal: Add computational analysis that reveals meaning patterns invisible to manual study.*

- [ ] **Semantic drift detection**
  - [ ] Train Word2Vec embeddings on Perseus secular corpus
  - [ ] Train separate embeddings on Christian patristic corpus
  - [ ] Compare vectors — flag lemmas with high divergence
  - [ ] Store results in drift_flags table
  - [ ] Display drift warnings in the UI

- [ ] **Frequency analysis**
  - [ ] Compute per-century, per-tradition frequency for each lemma
  - [ ] Visualize in UI (sparkline or bar chart per word)

- [ ] **LXX translation mapping**
  - [ ] For Septuagint text, link Greek words to underlying Hebrew/Aramaic
  - [ ] Display as additional data layer: "the LXX translators chose this word to render Hebrew X"
  - [ ] Flag where the Greek word's range doesn't match the Hebrew word's range

- [ ] **Comparison view**
  - [ ] UI for side-by-side secular vs. Christian definitions
  - [ ] Timeline view of meaning evolution per lemma

## Milestone 5: Expansion
*Goal: Broaden text coverage and data sources.*

- [ ] Additional Vaticanus books (Genesis, Psalms, Isaiah as high-value targets)
- [ ] Codex Sinaiticus integration (images are freely available from the British Library)
- [ ] Additional lexical sources as they become available
- [ ] Community contribution system for corrections and annotations
- [ ] Automated ingestion pipeline for new open-access lexical resources

---

## Non-Milestone / Ongoing

- [ ] Documentation: keep README, ARCHITECTURE, and CLAUDE.md current
- [ ] Testing: maintain test coverage for OCR, lexical engine, and API
- [ ] Performance: optimize SQLite queries as database grows
- [ ] Accessibility: ensure the web UI is usable with screen readers and keyboard navigation
- [ ] Internationalization: UI in multiple languages (the lexical data itself is multilingual by nature)
