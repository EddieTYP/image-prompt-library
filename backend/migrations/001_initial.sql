CREATE TABLE IF NOT EXISTS clusters (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  model TEXT NOT NULL DEFAULT 'ChatGPT Image2',
  media_type TEXT NOT NULL DEFAULT 'image',
  source_name TEXT,
  source_url TEXT,
  author TEXT,
  cluster_id TEXT,
  rating INTEGER NOT NULL DEFAULT 0,
  favorite INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  imported_at TEXT,
  FOREIGN KEY(cluster_id) REFERENCES clusters(id)
);
CREATE TABLE IF NOT EXISTS prompts (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  language TEXT NOT NULL,
  text TEXT NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  original_path TEXT NOT NULL,
  thumb_path TEXT,
  preview_path TEXT,
  remote_url TEXT,
  width INTEGER,
  height INTEGER,
  file_sha256 TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'general',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS item_tags (
  item_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  PRIMARY KEY(item_id, tag_id),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS imports (
  id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_path TEXT,
  source_url TEXT,
  status TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0,
  image_count INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  log TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS item_search USING fts5(
  item_id UNINDEXED,
  title,
  prompts,
  tags,
  cluster,
  source,
  notes
);
CREATE INDEX IF NOT EXISTS idx_items_cluster ON items(cluster_id);
CREATE INDEX IF NOT EXISTS idx_items_archived ON items(archived);
CREATE INDEX IF NOT EXISTS idx_prompts_item ON prompts(item_id);
CREATE INDEX IF NOT EXISTS idx_images_item ON images(item_id);
