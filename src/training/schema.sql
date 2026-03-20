-- Training dataset schema for OCR ground-truth labeling.
-- Stored in data/training/training.db (separate from the lexical database).

CREATE TABLE IF NOT EXISTS training_samples (
    id               INTEGER PRIMARY KEY,
    manuscript       TEXT    NOT NULL,
    folio            TEXT    NOT NULL,
    hand_id          TEXT    NOT NULL DEFAULT 'unknown'
                             CHECK(hand_id IN ('a', 'b', 'unknown')),
    line_image_path  TEXT    NOT NULL UNIQUE,   -- filename relative to data/training/images/
    source_line_bbox TEXT,                      -- JSON [x1,y1,x2,y2] in original folio coords
    column_index     INTEGER,
    ocr_guess        TEXT,                      -- pre-filled from Kraken output
    ground_truth     TEXT,                      -- human-confirmed transcription
    status           TEXT    NOT NULL DEFAULT 'pending'
                             CHECK(status IN ('pending', 'confirmed', 'skipped')),
    labeled_at       TEXT                       -- ISO 8601 datetime
);

-- Per-character bounding boxes within a line, derived from Kraken's cut positions.
CREATE TABLE IF NOT EXISTS training_chars (
    id              INTEGER PRIMARY KEY,
    sample_id       INTEGER NOT NULL REFERENCES training_samples(id) ON DELETE CASCADE,
    bbox_json       TEXT    NOT NULL,   -- JSON [x1,y1,x2,y2] relative to line image
    unicode_label   TEXT,               -- single Unicode codepoint, null until labeled
    ocr_char        TEXT,               -- what Kraken recognised (reference only)
    ocr_confidence  REAL                -- Kraken per-character confidence 0–1
);
