from pathlib import Path
from backend.db import MIGRATIONS, connect, init_db
import backend.db as db_module


def test_init_db_creates_required_tables(tmp_path: Path):
    library = tmp_path / "library"
    db_path = init_db(library)
    assert db_path == library / "db.sqlite"
    with connect(library) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        assert {"items", "prompts", "images", "clusters", "tags", "item_tags", "imports", "item_search", "schema_migrations"} <= tables
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        image_columns = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
        assert {"role", "generation_provider", "generation_model"} <= image_columns
        images_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='images'").fetchone()[0]
        assert "CHECK(role IN ('result_image', 'reference_image'))" in images_sql
        prompt_columns = {row[1] for row in conn.execute("PRAGMA table_info(prompts)")}
        assert {"is_original", "provenance"} <= prompt_columns
        cluster_columns = {row[1] for row in conn.execute("PRAGMA table_info(clusters)")}
        assert "names" in cluster_columns
        assert {row[0] for row in conn.execute("SELECT version FROM schema_migrations")} == set(MIGRATIONS)


def test_init_db_is_idempotent(tmp_path: Path):
    init_db(tmp_path / "library")
    init_db(tmp_path / "library")
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)
        assert {row[0] for row in conn.execute("SELECT version FROM schema_migrations")} == set(MIGRATIONS)


def test_generation_jobs_source_created_index_is_migrated(tmp_path: Path):
    library = tmp_path / "library"
    init_db(library)

    with connect(library) as conn:
        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list('generation_jobs')")
        }
        columns = [
            (row["name"], row["desc"])
            for row in conn.execute(
                "PRAGMA index_xinfo('idx_generation_jobs_source_created')"
            )
            if row["key"]
        ]

    assert "idx_generation_jobs_source_created" in indexes
    assert columns == [("source_item_id", 0), ("created_at", 1)]


def test_failed_destructive_migration_rolls_back_and_can_retry(tmp_path: Path, monkeypatch):
    library = tmp_path / "library"
    init_db(library)
    with connect(library) as conn:
        conn.execute("DELETE FROM schema_migrations")
        conn.commit()

    original_read_text = Path.read_text
    migration_sql = {"value": "CREATE TABLE destructive_new(id TEXT);\nDROP TABLE items;\nTHIS IS INVALID;"}

    def read_text(path, *args, **kwargs):
        if path.name == "failure.sql":
            return migration_sql["value"]
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(db_module, "MIGRATIONS", ["failure.sql"])

    try:
        init_db(library)
    except Exception:
        pass
    else:
        raise AssertionError("broken migration unexpectedly succeeded")
    with connect(library) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'").fetchone()
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='destructive_new'").fetchone()
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0

    migration_sql["value"] = "CREATE TABLE retry_table(id TEXT);"
    init_db(library)
    with connect(library) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='retry_table'").fetchone()
        assert conn.execute("SELECT version FROM schema_migrations").fetchone()[0] == "failure.sql"
