# TODO — Roadmap

## Milestone 0: Project Foundation
- [x] Initialize repository structure (directories, configs)
- [x] Set up Python project with pyproject.toml (dependencies: cltk, kraken, fastapi, requests, beautifulsoup4, gensim)
- [x] Set up frontend project with Vite + React + TypeScript
- [x] Create SQLite schema and initialization script
- [x] Write CONTRIBUTING.md with guidelines for contributors
- [x] Set up basic CI (linting, tests)

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

## Milestone 2.5: OCR Training Dataset
*Goal: Build a labeled character/line dataset from the Codex Vaticanus to train hand-specific OCR models.*

The Vaticanus has two distinct scribal hands that require separate models:
- **Hand A** — folios 1–40 (distinct script style)
- **Hand B** — folios 41+ (main scribe, currently targeted by the pipeline)

### Character Detection
- [ ] Implement connected component analysis on binarized line images to extract candidate glyph bboxes
- [ ] Merge split components (multi-part glyphs like Θ, Φ — vertical overlap heuristic)
- [ ] Split fused touching characters using projection profile valley detection
- [ ] Filter noise by aspect ratio and area thresholds
- [ ] Store per-character bounding boxes in `training.db` linked to their parent line

### Training Data Storage
- [ ] Define `training_samples` SQLite schema: `(id, manuscript, folio, hand_id, line_image_path, ocr_guess, ground_truth, status, labeled_at)`
- [ ] Define `training_chars` schema: `(id, sample_id, bbox_json, unicode_label)`
- [ ] Create `data/training/` directory layout: `images/`, `ground_truth/`, `chars/`
- [ ] Script to extract and save line crops from existing OCR output into `data/training/images/`

### Labeling API (`src/api/routes/training.py`)
- [ ] `GET /training/lines` — list lines with label status, filterable by hand and folio
- [ ] `GET /training/lines/{id}` — return line image path, OCR guess, and character bboxes
- [ ] `POST /training/lines/{id}/label` — save confirmed ground truth transcription
- [ ] `POST /training/lines/{id}/chars/{char_id}/label` — label individual character (for char-level review mode)
- [ ] `GET /training/export` — trigger export of confirmed labels to Kraken training format

### Labeling UI (`src/frontend/src/components/LabelingView.tsx`)
- [ ] Main labeling layout: line image above, transcription input below
- [ ] Character box overlay on line image (togglable, highlights detected glyph boundaries)
- [ ] Pre-fill OCR guess into transcription field as editable starting point
- [ ] **Virtual keyboard** covering the full Vaticanus character set:
  - 24 uppercase Greek letters (Α Β Γ Δ Ε Ζ Η Θ Ι Κ Λ Μ Ν Ξ Ο Π Ρ Σ Τ Υ Φ Χ Ψ Ω)
  - Lunate sigma (Ϲ) — the form actually used in the manuscript
  - Punctuation: high dot (·), dicolon (÷), paragraph mark (¶)
  - Nomina sacra buttons with combining overline (U+0305): ΙΣ̄ ΧΣ̄ ΘΣ̄ ΚΣ̄ ΠΝᾹ
  - Greek numeral markers (combining overline for numeric use)
  - Diacritic/corrector marks as a secondary panel (breathing marks, accents — for corrector hands only)
- [ ] Hand selector: tag each session as Hand A (folios 1–40) or Hand B (folios 41+)
- [ ] Progress bar: labeled / total per hand
- [ ] Keyboard shortcuts: Enter to confirm + advance, Arrow keys to navigate, Tab to skip

### Transcription Validation
- [ ] Reject characters outside the Vaticanus character set with a visible warning
- [ ] Flag suspiciously short transcriptions relative to detected character count
- [ ] Detect probable nomina sacra sequences (common abbreviation patterns) and warn if overline is missing

### Line Segmentation Training
*Current pageseg (rule-based, scale=30) produces poor line boundaries. Replace with a BLLA neural segmenter trained on Vaticanus ground truth.*

- [ ] **Segmentation ground truth authoring**
  - [ ] Add bbox-editing mode to the HTML labeling interface: drag to adjust line bboxes, add/delete lines
  - [ ] Export corrected line bboxes from the labeling interface as PAGE XML (the format `ketos segtrain` requires)
  - [ ] Script `scripts/export_seg_gt.py`: reads labeled JSON + corrections → writes PAGE XML into `data/training/seg_gt/`
  - [ ] Aim for ≥ 5 fully corrected folios as initial training set

- [ ] **BLLA segmentation model training**
  - [ ] Verify `ketos segtrain` is available in the `aenigmata` conda env
  - [ ] `scripts/train_seg.py` — wrapper for `ketos segtrain` with project-standard paths and train/eval split
  - [ ] Train initial model: `ketos segtrain -d data/training/seg_gt/ -o data/models/seg_vat_blla`
  - [ ] Evaluate on held-out folio; compare line count and boundary quality against pageseg baseline
  - [ ] Document training command and model path in CLAUDE.md once first model is validated

- [ ] **Pipeline integration**
  - [ ] Update `src/ocr/recognize.py` to accept `--seg-model` flag pointing to a trained BLLA model
  - [ ] When `--seg-model` is provided, call `blla.segment()` instead of `pageseg.segment()`
  - [ ] Keep pageseg as the fallback when no seg model is specified
  - [ ] Add model path to CLAUDE.md once a satisfactory model is produced

### Recognition Model Training
- [ ] `scripts/export_training.py` — write confirmed labels as Kraken training pairs: `line_XXXX.png` + `line_XXXX.gt.txt`
- [ ] Separate exports per hand: `data/training/hand_a/` and `data/training/hand_b/`
- [ ] 90/10 train/eval split per hand
- [ ] Document `ketos train` fine-tuning command in CLAUDE.md once first export is validated

---

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
