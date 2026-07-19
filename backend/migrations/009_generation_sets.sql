ALTER TABLE generation_jobs ADD COLUMN generation_group_id TEXT;
ALTER TABLE generation_jobs ADD COLUMN generation_group_index INTEGER;
ALTER TABLE generation_jobs ADD COLUMN generation_group_size INTEGER;

CREATE TABLE IF NOT EXISTS generation_sets (
  generation_group_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  total INTEGER NOT NULL CHECK(total IN (1, 3, 5, 10)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_queue_states (
  provider TEXT PRIMARY KEY,
  paused_until TEXT,
  retry_after_seconds INTEGER NOT NULL DEFAULT 0,
  backoff_seconds INTEGER NOT NULL DEFAULT 0,
  incident_count INTEGER NOT NULL DEFAULT 0,
  wave_active INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_generation_jobs_group ON generation_jobs(generation_group_id, generation_group_index);
CREATE INDEX IF NOT EXISTS idx_generation_sets_provider ON generation_sets(provider, created_at DESC);
