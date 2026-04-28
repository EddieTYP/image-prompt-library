CREATE TABLE IF NOT EXISTS import_drafts (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'staged' CHECK(status IN ('staged', 'duplicate', 'accepted', 'discarded')),
  source_type TEXT NOT NULL,
  source_name TEXT,
  source_url TEXT,
  source_ref TEXT,
  source_path TEXT,
  title TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT 'ChatGPT Image2',
  author TEXT,
  suggested_cluster_name TEXT,
  suggested_tags TEXT NOT NULL DEFAULT '[]',
  prompts TEXT NOT NULL DEFAULT '[]',
  media TEXT NOT NULL DEFAULT '[]',
  warnings TEXT NOT NULL DEFAULT '[]',
  confidence REAL,
  duplicate_of_item_id TEXT,
  accepted_item_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  accepted_at TEXT,
  FOREIGN KEY(duplicate_of_item_id) REFERENCES items(id) ON DELETE SET NULL,
  FOREIGN KEY(accepted_item_id) REFERENCES items(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_import_drafts_status ON import_drafts(status);
CREATE INDEX IF NOT EXISTS idx_import_drafts_source_url ON import_drafts(source_url);
CREATE INDEX IF NOT EXISTS idx_import_drafts_duplicate ON import_drafts(duplicate_of_item_id);
