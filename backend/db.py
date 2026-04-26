import sqlite3
from pathlib import Path
from .config import resolve_library_path

MIGRATIONS = ["001_initial.sql", "002_image_roles.sql", "003_image_role_check.sql"]

def get_db_path(library_path=None) -> Path:
    return resolve_library_path(library_path) / "db.sqlite"

def connect(library_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(library_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(library_path=None) -> Path:
    library = resolve_library_path(library_path)
    db_path = library / "db.sqlite"
    with connect(library) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for migration in MIGRATIONS:
            if migration not in done:
                sql = (Path(__file__).parent / "migrations" / migration).read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))", (migration,))
        conn.commit()
    return db_path
