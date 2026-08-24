CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    path TEXT NOT NULL,
    preview_path TEXT,
    size_bytes INTEGER NOT NULL,
    duration REAL,
    width INTEGER,
    height INTEGER,
    audio_present INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_media_assets (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, asset_id)
);

ALTER TABLE media_references ADD COLUMN asset_id TEXT REFERENCES media_assets(id) ON DELETE SET NULL;
ALTER TABLE media_references ADD COLUMN notes TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_media_assets_sha256 ON media_assets(sha256);
CREATE INDEX IF NOT EXISTS idx_project_media_assets_project ON project_media_assets(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_media_references_asset ON media_references(asset_id);
