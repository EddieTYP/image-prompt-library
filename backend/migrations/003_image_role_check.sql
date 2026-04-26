PRAGMA foreign_keys=off;

CREATE TABLE images_new (
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
  role TEXT NOT NULL DEFAULT 'result_image' CHECK(role IN ('result_image', 'reference_image')),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

INSERT INTO images_new(id,item_id,original_path,thumb_path,preview_path,remote_url,width,height,file_sha256,sort_order,created_at,role)
SELECT id,item_id,original_path,thumb_path,preview_path,remote_url,width,height,file_sha256,sort_order,created_at,
  CASE WHEN role IN ('result_image', 'reference_image') THEN role ELSE 'result_image' END
FROM images;

DROP TABLE images;
ALTER TABLE images_new RENAME TO images;
CREATE INDEX IF NOT EXISTS idx_images_item ON images(item_id);
CREATE INDEX IF NOT EXISTS idx_images_item_role ON images(item_id, role);

PRAGMA foreign_keys=on;
