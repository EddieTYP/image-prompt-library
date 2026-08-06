CREATE INDEX IF NOT EXISTS idx_generation_jobs_source_created
ON generation_jobs(source_item_id, created_at DESC);
