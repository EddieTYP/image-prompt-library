ALTER TABLE images ADD COLUMN role TEXT NOT NULL DEFAULT 'result_image';
CREATE INDEX IF NOT EXISTS idx_images_item_role ON images(item_id, role);
