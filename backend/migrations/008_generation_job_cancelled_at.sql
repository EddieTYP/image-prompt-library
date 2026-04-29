CREATE TABLE generation_jobs_new (
  id TEXT PRIMARY KEY,
  source_item_id TEXT,
  mode TEXT NOT NULL DEFAULT 'text_to_image' CHECK(mode IN ('text_to_image', 'text_reference_to_image', 'image_edit')),
  provider TEXT NOT NULL DEFAULT 'manual_upload',
  model TEXT,
  status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued', 'running', 'succeeded', 'failed', 'accepted', 'discarded', 'cancelled')),
  prompt_language TEXT,
  prompt_text TEXT NOT NULL,
  edited_prompt_text TEXT,
  reference_image_ids TEXT NOT NULL DEFAULT '[]',
  parameters TEXT NOT NULL DEFAULT '{}',
  result_path TEXT,
  result_width INTEGER,
  result_height INTEGER,
  result_sha256 TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  accepted_image_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  accepted_at TEXT,
  discarded_at TEXT,
  cancelled_at TEXT,
  FOREIGN KEY(source_item_id) REFERENCES items(id) ON DELETE SET NULL,
  FOREIGN KEY(accepted_image_id) REFERENCES images(id) ON DELETE SET NULL
);

INSERT INTO generation_jobs_new(
  id, source_item_id, mode, provider, model, status, prompt_language,
  prompt_text, edited_prompt_text, reference_image_ids, parameters,
  result_path, result_width, result_height, result_sha256, metadata, error,
  accepted_image_id, created_at, updated_at, started_at, completed_at,
  accepted_at, discarded_at, cancelled_at
)
SELECT
  id, source_item_id, mode, provider, model, status, prompt_language,
  prompt_text, edited_prompt_text, reference_image_ids, parameters,
  result_path, result_width, result_height, result_sha256, metadata, error,
  accepted_image_id, created_at, updated_at, started_at, completed_at,
  accepted_at, discarded_at, NULL
FROM generation_jobs;

DROP TABLE generation_jobs;
ALTER TABLE generation_jobs_new RENAME TO generation_jobs;

CREATE INDEX IF NOT EXISTS idx_generation_jobs_status_created ON generation_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_source_item ON generation_jobs(source_item_id);
