-- aenigmata lexical database schema
-- Period convention: century integers, negative = BCE (e.g., -5 = 5th century BCE, 5 = 5th century CE)
-- Confidence values: REAL in range 0.0000–1.0000

-- Core lemma table
CREATE TABLE IF NOT EXISTS lemmas (
    id INTEGER PRIMARY KEY,
    lemma TEXT NOT NULL,          -- dictionary form (e.g., λόγος)
    transliteration TEXT,         -- ASCII transliteration
    pos TEXT,                     -- part of speech
    morphology_json TEXT          -- full morphological paradigm
);

-- Sources (lexicons, dictionaries, corpora)
-- Declared first because definitions/attestations reference it.
-- New sources: register here + write a script in src/lexicon/ingest/.
-- type: 'lexicon' | 'corpus' | 'derived'
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- e.g., "Perseus Middle Liddell"
    type TEXT NOT NULL,           -- 'lexicon', 'corpus', 'derived'
    date TEXT,                    -- when the source was created
    tradition TEXT,               -- interpretive tradition if any
    url TEXT,                     -- where to find it
    license TEXT NOT NULL,        -- licensing information (required)
    bias_notes TEXT               -- known biases or limitations
);

-- Definitions from specific sources
-- source_id and lemma_id are NOT NULL — no orphaned definitions allowed.
-- confidence: 0.0000–1.0000, attestation strength across corpus (not OCR probability)
CREATE TABLE IF NOT EXISTS definitions (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    definition TEXT NOT NULL,     -- the definition text
    period_start INTEGER,         -- century (e.g., -5 = 5th century BCE)
    period_end INTEGER,           -- century (e.g., 5 = 5th century CE)
    tradition TEXT,               -- 'secular', 'christian', 'jewish', 'philosophical', etc.
    original_language TEXT,       -- language the definition is written in
    confidence REAL               -- 0.0000–1.0000: attestation strength across corpus
);

-- Usage attestations from actual texts
-- source_id and lemma_id are NOT NULL.
CREATE TABLE IF NOT EXISTS attestations (
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
CREATE TABLE IF NOT EXISTS semantic_fields (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    field_name TEXT NOT NULL,     -- e.g., "speech/discourse", "reason/rationality"
    modern_equivalents TEXT,      -- JSON array of modern-language approximations
    notes TEXT                    -- what's lost or gained in each mapping
);

-- Cross-references between lemmas
CREATE TABLE IF NOT EXISTS cross_references (
    id INTEGER PRIMARY KEY,
    from_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    to_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    relationship TEXT,            -- 'synonym', 'antonym', 'semantic_field', 'derived', etc.
    notes TEXT
);

-- Semantic drift detection
-- References definitions table — no text duplication.
-- divergence_score: 0.0000–1.0000 (e.g., cosine distance between embedding centroids)
-- evidence: JSON array of definition IDs used in the divergence computation
CREATE TABLE IF NOT EXISTS drift_flags (
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
--   lemma assignment are correct (may reflect multiple competing parses)
CREATE TABLE IF NOT EXISTS token_lemma_links (
    id INTEGER PRIMARY KEY,
    manuscript TEXT NOT NULL,
    folio TEXT NOT NULL,
    token_id TEXT NOT NULL,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    morphological_form TEXT,      -- specific form in text (e.g., λόγον = acc.sg.)
    parse TEXT,                   -- full morphological parse
    confidence REAL               -- 0.0000–1.0000: parse/lemma assignment confidence
);
