from pathlib import Path
from backend.db import connect, init_db


def test_init_db_creates_required_tables(tmp_path: Path):
    library = tmp_path / "library"
    db_path = init_db(library)
    assert db_path == library / "db.sqlite"
    with connect(library) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        assert {"items", "prompts", "images", "clusters", "tags", "item_tags", "imports", "item_search", "schema_migrations"} <= tables
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_init_db_is_idempotent(tmp_path: Path):
    init_db(tmp_path / "library")
    init_db(tmp_path / "library")
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
