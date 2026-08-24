ALTER TABLE generations ADD COLUMN output_metadata_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE generations ADD COLUMN comfy_prompt_id TEXT;
ALTER TABLE generations ADD COLUMN execution_seconds REAL;
ALTER TABLE generations ADD COLUMN model_manifest_version TEXT;
