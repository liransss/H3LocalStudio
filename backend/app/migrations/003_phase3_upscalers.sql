CREATE TABLE IF NOT EXISTS generation_variants (
    id TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    variant TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    duration REAL,
    audio_present INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(generation_id, variant)
);

CREATE INDEX IF NOT EXISTS idx_generation_variants_generation
ON generation_variants(generation_id, variant);

ALTER TABLE jobs ADD COLUMN execution_metadata_json TEXT NOT NULL DEFAULT '{}';
