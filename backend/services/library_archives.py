"""Portable, local-only library backup, verification, and restore.

The archive format is deliberately small: a JSON manifest at the archive root
and regular files below ``library/``.  Credentials, configuration, logs, and
other app state are never traversed or copied.
"""

from __future__ import annotations

import gc
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tarfile
import tempfile
import unicodedata
import uuid
import zlib
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterator

from backend import config, db

ARCHIVE_FORMAT = "image-prompt-library"
ARCHIVE_VERSION = 1
MANIFEST_NAME = "manifest.json"
LIBRARY_PREFIX = "library"
MANIFEST_KEYS = {
    "format",
    "format_version",
    "app_version",
    "created_at",
    "required_storage_roots",
    "migrations",
    "total_size",
    "files",
}
REQUIRED_STORAGE_ROOTS = (
    "originals",
    "thumbs",
    "previews",
    "generation-results",
    "generation-references",
)

# Limits are intentionally conservative enough to avoid archive bombs while
# allowing normal personal libraries.  Tests and packaged callers may inspect
# these constants rather than relying on implementation details.
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_MEMBER_COUNT = 100_000
MAX_FILE_SIZE = 64 * 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_SIZE = 1024 * 1024 * 1024 * 1024
_REPARSE_POINT = 0x0400
_WINDOWS_RESERVED_BASENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
LAST_PRESERVED_PATH: Path | None = None


class LibraryArchiveError(ValueError):
    """An actionable archive operation failure."""


class _TrackedGzipReader(gzip.GzipFile):
    """Remember the last tar-sized block read without replaying the gzip stream."""

    last_tar_block: bytes | None = None

    def read(self, size: int = -1) -> bytes:
        data = super().read(size)
        if size == tarfile.BLOCKSIZE:
            self.last_tar_block = data
        return data


def _error(message: str) -> LibraryArchiveError:
    return LibraryArchiveError(message)


def _validate_tar_end(first_end_block: bytes | None, trailing: bytes) -> None:
    zero_block = b"\0" * tarfile.BLOCKSIZE
    if first_end_block != zero_block or trailing[: tarfile.BLOCKSIZE] != zero_block:
        raise _error("Backup archive has an invalid or incomplete tar end marker")
    padding = trailing[tarfile.BLOCKSIZE :]
    if len(trailing) > tarfile.RECORDSIZE or any(padding):
        raise _error("Backup archive contains unexpected data after the tar end marker")


def _path_identities(path: Path | str) -> tuple[Path, Path]:
    absolute = Path(os.path.abspath(Path(path).expanduser()))
    try:
        return absolute, absolute.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise _error(f"Could not safely resolve path: {absolute}") from exc


def _within(candidate: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(candidate)), os.path.normcase(str(root)))) == os.path.normcase(str(root))
    except ValueError:
        return False


def _is_reparse_or_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & _REPARSE_POINT)
    except OSError as exc:
        raise _error(f"Could not inspect path safely: {path}") from exc


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_regular_source(path: Path) -> tuple[BinaryIO, os.stat_result]:
    """Open one payload file without following a swapped link."""

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or _is_reparse_or_link(path):
            raise _error(f"Library payload contains a symlink/reparse point: {path}")
        fd = os.open(path, flags)
    except LibraryArchiveError:
        raise
    except OSError as exc:
        raise _error(f"Could not safely open library file: {path}") from exc
    try:
        opened = os.fstat(fd)
        after = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink > 1
            or not _same_file_identity(before, opened)
            or not _same_file_identity(opened, after)
        ):
            raise _error(f"Library payload changed or is not a private regular file: {path}")
        return os.fdopen(fd, "rb"), opened
    except Exception:
        os.close(fd)
        raise


def _assert_directory(path: Path, *, label: str, required: bool = True) -> bool:
    if not path.exists():
        if os.path.lexists(path):
            raise _error(f"{label} is an unsafe or broken link: {path}")
        if required:
            raise _error(f"{label} does not exist: {path}")
        return False
    if _is_reparse_or_link(path) or not path.is_dir():
        raise _error(f"{label} must be a real directory (not a symlink/reparse point): {path}")
    return True


def _assert_active_library(library: Path, *, must_exist: bool = True) -> bool:
    exists = _assert_directory(library, label="Active library", required=must_exist)
    try:
        config.validate_app_owned_paths(library)
    except ValueError as exc:
        raise _error(str(exc)) from exc
    if not exists:
        return False
    for root_name in REQUIRED_STORAGE_ROOTS:
        root = library / root_name
        if root.exists():
            _assert_directory(root, label=f"Library storage root {root_name}")
    return True


def _assert_outside_library(path: Path, library: Path, *, label: str) -> None:
    absolute, resolved = _path_identities(path)
    library_absolute, library_resolved = _path_identities(library)
    # Check both lexical and resolved identities.  The parent may not exist yet.
    if _within(absolute, library_absolute) or _within(resolved, library_resolved):
        raise _error(f"{label} must resolve outside the active library: {absolute}")


def _safe_component(component: str) -> None:
    if not component or component in {".", ".."}:
        raise _error("Archive path contains an invalid component")
    if any(ord(char) < 32 or ord(char) == 127 for char in component):
        raise _error(f"Archive path contains a control character: {component!r}")
    if component.endswith((".", " ")) or ":" in component or "\\" in component:
        raise _error(f"Archive path contains an unsafe component: {component!r}")
    basename = component.split(".", 1)[0].upper()
    if basename in _WINDOWS_RESERVED_BASENAMES:
        raise _error(f"Archive path contains a Windows-reserved basename: {component!r}")


def _collision_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _canonical_relative(value: str | Path, *, require_file_root: bool = True) -> str:
    raw = str(value)
    if "\\" in raw:
        raise _error(f"Archive path must use canonical POSIX separators: {raw!r}")
    p = PurePosixPath(raw)
    if p.is_absolute() or not p.parts:
        raise _error(f"Archive path must be relative: {raw!r}")
    if any(part in {".", ".."} for part in p.parts):
        raise _error(f"Archive path contains traversal: {raw!r}")
    for part in p.parts:
        _safe_component(part)
    if require_file_root and (p.parts[0] not in {"db.sqlite", *REQUIRED_STORAGE_ROOTS}):
        raise _error(f"Archive path is outside the library payload allowlist: {raw!r}")
    canonical = p.as_posix()
    if canonical != raw:
        raise _error(f"Archive path is not canonical: {raw!r}")
    return canonical


def _canonical_member(name: str) -> str:
    if "\\" in name or name.startswith("/") or name.startswith("//"):
        raise _error(f"Archive member has an unsafe path: {name!r}")
    # A Windows drive/UNC path and ADS both contain a colon; reject all colons.
    return PurePosixPath(_canonical_relative(name, require_file_root=False)).as_posix()


def _file_hash(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    try:
        handle, opened = _open_regular_source(path)
        if opened.st_size > MAX_FILE_SIZE:
            handle.close()
            raise _error(f"Library file exceeds the per-file size limit: {path}")
        with handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            final = os.fstat(handle.fileno())
    except OSError as exc:
        raise _error(f"Could not read library file: {path}") from exc
    if final.st_size != opened.st_size or not _same_file_identity(opened, final):
        raise _error(f"Library file changed while it was being read: {path}")
    return opened.st_size, digest.hexdigest()


def _stage_file(source: Path, destination: Path, expected_size: int, expected_hash: str) -> None:
    digest = hashlib.sha256()
    written = 0
    try:
        source_handle, opened = _open_regular_source(source)
        with source_handle, destination.open("xb") as output:
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                written += len(chunk)
                if written > MAX_FILE_SIZE:
                    raise _error(f"Library file exceeds the per-file size limit: {source}")
                digest.update(chunk)
                output.write(chunk)
            final = os.fstat(source_handle.fileno())
    except LibraryArchiveError:
        raise
    except OSError as exc:
        raise _error(f"Could not stage library file: {source}") from exc
    if (
        written != expected_size
        or digest.hexdigest() != expected_hash
        or final.st_size != opened.st_size
        or not _same_file_identity(opened, final)
    ):
        raise _error(f"Library file changed during backup: {source}")


def _iter_payload_files(library: Path) -> list[tuple[str, Path, int, str]]:
    entries: list[tuple[str, Path, int, str]] = []
    seen_case: set[str] = set()
    total = 0

    def add_file(relative: str, source: Path) -> None:
        nonlocal total
        canonical = _canonical_relative(relative)
        key = _collision_key(canonical)
        if key in seen_case:
            raise _error(f"Library payload contains duplicate/case-colliding path: {canonical}")
        seen_case.add(key)
        size, digest = _file_hash(source)
        total += size
        if total > MAX_TOTAL_UNCOMPRESSED_SIZE:
            raise _error("Library payload exceeds the total uncompressed size limit")
        entries.append((canonical, source, size, digest))
        if len(entries) > MAX_MEMBER_COUNT:
            raise _error("Library payload exceeds the member-count limit")

    db_path = library / "db.sqlite"
    if not db_path.exists():
        raise _error(f"Active library database does not exist: {db_path}")
    if _is_reparse_or_link(db_path):
        raise _error("Active library database must not be a symlink/reparse point")
    add_file("db.sqlite", db_path)

    def walk(root: Path, rel_root: str) -> None:
        if not root.exists():
            return
        if _is_reparse_or_link(root) or not root.is_dir():
            raise _error(f"Library storage root must be a real directory: {root}")
        try:
            children = sorted(root.iterdir(), key=lambda p: _collision_key(p.name))
        except OSError as exc:
            raise _error(f"Could not enumerate library storage root: {root}") from exc
        for child in children:
            _safe_component(child.name)
            relative = f"{rel_root}/{child.name}"
            if _is_reparse_or_link(child):
                raise _error(f"Library payload contains a symlink/reparse point: {child}")
            if child.is_dir():
                walk(child, relative)
            elif child.is_file():
                add_file(relative, child)
            else:
                raise _error(f"Library payload contains a non-regular file: {child}")

    for root_name in REQUIRED_STORAGE_ROOTS:
        walk(library / root_name, root_name)
    return sorted(entries, key=lambda row: row[0])


def _migration_ledger(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY rowid").fetchall()
    except sqlite3.Error as exc:
        raise _error("Library database has no readable schema migration ledger") from exc
    ledger = [str(row[0]) for row in rows]
    if len(ledger) > len(db.MIGRATIONS) or ledger != db.MIGRATIONS[: len(ledger)]:
        raise _error("Library database migration ledger is not an exact known prefix")
    if len(set(ledger)) != len(ledger):
        raise _error("Library database migration ledger contains duplicate versions")
    return ledger


def _validate_schema_contract(conn: sqlite3.Connection, ledger: list[str]) -> None:
    migration_count = len(ledger)
    required_tables = {"schema_migrations"}
    if migration_count >= 1:
        required_tables.update({"clusters", "items", "prompts", "images", "tags", "item_tags", "imports", "item_search"})
    if migration_count >= 6:
        required_tables.add("import_drafts")
    if migration_count >= 7:
        required_tables.add("generation_jobs")
    if migration_count >= 9:
        required_tables.update({"generation_sets", "provider_queue_states"})
    schema_objects = {
        str(row[0]): (str(row[1]), str(row[2] or ""))
        for row in conn.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view')")
    }
    missing_tables = sorted(name for name in required_tables if schema_objects.get(name, (None,))[0] != "table")
    if missing_tables:
        raise _error(f"Library database schema is missing required table: {missing_tables[0]}")
    for name in required_tables - {"item_search"}:
        if "CREATE VIRTUAL TABLE" in schema_objects[name][1].upper():
            raise _error(f"Library database schema has an invalid virtual table: {name}")
    if "item_search" in required_tables:
        item_search_sql = schema_objects["item_search"][1].upper()
        if "CREATE VIRTUAL TABLE" not in item_search_sql or "USING FTS5" not in item_search_sql:
            raise _error("Library database schema has an invalid item_search table")

    required_columns: dict[str, set[str]] = {}
    if migration_count >= 2:
        required_columns.setdefault("images", set()).add("role")
    if migration_count >= 4:
        required_columns.setdefault("prompts", set()).update({"is_original", "provenance"})
    if migration_count >= 5:
        required_columns.setdefault("clusters", set()).add("names")
    if migration_count >= 8:
        required_columns.setdefault("generation_jobs", set()).add("cancelled_at")
    if migration_count >= 9:
        required_columns.setdefault("generation_jobs", set()).update(
            {"generation_group_id", "generation_group_index", "generation_group_size"}
        )
    for table, expected in required_columns.items():
        actual = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        missing_columns = sorted(expected - actual)
        if missing_columns:
            raise _error(f"Library database schema is missing required column: {table}.{missing_columns[0]}")


def _validate_database(path: Path, *, library: Path | None = None) -> list[str]:
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise _error(f"SQLite integrity_check failed: {integrity[0] if integrity else 'no result'}")
        foreign = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign:
            raise _error("SQLite foreign_key_check failed")
        ledger = _migration_ledger(conn)
        _validate_schema_contract(conn, ledger)
        if library is not None:
            _validate_referenced_paths(conn, library)
        return ledger
    except LibraryArchiveError:
        raise
    except sqlite3.Error as exc:
        raise _error(f"Could not validate SQLite database: {path}") from exc
    finally:
        if conn is not None:
            conn.close()


def _validate_referenced_paths(conn: sqlite3.Connection, library: Path) -> None:
    def validate(value: Any, label: str, *, required: bool = False) -> None:
        if value is None or value == "":
            if required:
                raise _error(f"Database {label} must reference a library file")
            return
        if not isinstance(value, str):
            raise _error(f"Database {label} is not a path string")
        rel = _canonical_relative(value)
        if rel == "db.sqlite":
            raise _error(f"Database {label} points at db.sqlite instead of library media")
        target = library / Path(*PurePosixPath(rel).parts)
        if not _within(target, library) or not target.is_file() or _is_reparse_or_link(target):
            raise _error(f"Database {label} references a missing or unsafe library file: {value}")

    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
        if columns:
            selected = [name for name in ("original_path", "thumb_path", "preview_path") if name in columns]
            for row in conn.execute(f"SELECT {','.join(selected)} FROM images"):
                for name, value in zip(selected, row):
                    validate(value, f"images.{name}", required=name == "original_path")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(generation_jobs)")}
        if "result_path" in columns:
            for row in conn.execute("SELECT result_path FROM generation_jobs"):
                validate(row[0], "generation_jobs.result_path")
    except sqlite3.Error as exc:
        raise _error("Could not validate database library references") from exc


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(payload) > MAX_MANIFEST_BYTES:
        raise _error("Archive manifest exceeds the size limit")
    return payload


def _json_no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"Backup manifest contains a duplicate JSON key: {key}")
        result[key] = value
    return result


def _add_bytes(tar: tarfile.TarFile, name: str, payload: bytes, mode: int = 0o600) -> None:
    from io import BytesIO

    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = mode
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tar.addfile(info, BytesIO(payload))


def _add_file(tar: tarfile.TarFile, name: str, source: Path, expected_size: int, expected_hash: str) -> None:
    info = tarfile.TarInfo(name)
    info.size = expected_size
    info.mode = 0o600
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    try:
        with source.open("rb") as handle:
            tar.addfile(info, handle)
    except OSError as exc:
        raise _error(f"Could not archive library file: {source}") from exc
    # tarfile.addfile consumed the stream itself; hash with a second pass only
    # to detect a source that changed while the operation was running.
    size, actual_hash = _file_hash(source)
    if size != expected_size or actual_hash != expected_hash:
        raise _error(f"Library file changed during backup: {source}")


def _default_backup_path(library: Path, backup_dir: Path | None) -> Path:
    directory = (backup_dir or Path(os.environ.get("BACKUP_DIR", library.parent / "backups")).expanduser()).absolute()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"image-prompt-library-{timestamp}-{uuid.uuid4().hex[:8]}.tar.gz"


def _require_free_space(path: Path, required: int, *, operation: str) -> None:
    try:
        available = shutil.disk_usage(path).free
    except OSError as exc:
        raise _error(f"Could not determine free disk space for {operation}: {path}") from exc
    if available < required:
        raise _error(f"Insufficient disk space to stage the {operation} safely")


def _sync_directory(path: Path) -> None:
    """Best-effort directory sync; full power-loss recovery remains out of scope."""

    if os.name != "posix":
        return
    fd: int | None = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(fd)
    except OSError:
        # Some otherwise supported filesystems do not permit directory fsync.
        pass
    finally:
        if fd is not None:
            os.close(fd)


@contextmanager
def _claim_archive_output(output: Path) -> Iterator[None]:
    """Prevent cooperating processes from publishing to the same output."""

    lock_path = output.parent / ".image-prompt-library-backup-output.lock"
    message = f"Archive output is already being created; retry after it finishes: {output}"
    with LibraryOperationLock(output.parent, _lock_path=lock_path, _busy_message=message):
        if os.path.lexists(output):
            raise _error(f"Archive output already exists; choose a new path: {output}")
        yield


def _resolve_library_arg(library_path: Path | str | None, *, create_default: bool = True) -> Path:
    if library_path is None:
        if create_default:
            return config.resolve_library_path()
        configured = os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
        return Path(configured).expanduser().absolute() if configured else config.DEFAULT_LIBRARY_PATH.absolute()
    return Path(library_path).expanduser().absolute()


class LibraryOperationLock:
    """A non-blocking sibling lock shared by backup/verify/restore operations."""

    def __init__(
        self,
        library_path: Path | str,
        *,
        _lock_path: Path | None = None,
        _busy_message: str | None = None,
    ):
        if _lock_path is None:
            _, library = _path_identities(library_path)
            self.path = library.parent / f".{library.name}.library-operation.lock"
        else:
            self.path = _lock_path
        self._busy_message = _busy_message or (
            f"Library operation is busy; stop the running app or other backup/restore operation and retry ({self.path})"
        )
        self._handle = None

    def acquire(self) -> "LibraryOperationLock":
        if self._handle is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            before = self.path.lstat() if os.path.lexists(self.path) else None
            if before is not None and (stat.S_ISLNK(before.st_mode) or _is_reparse_or_link(self.path)):
                raise _error(f"Library operation lock path is unsafe: {self.path}")
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            opened = os.fstat(fd)
            after = self.path.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink > 1
                or (before is not None and not _same_file_identity(before, opened))
                or not _same_file_identity(opened, after)
            ):
                os.close(fd)
                raise _error(f"Library operation lock path is unsafe: {self.path}")
            try:
                self._handle = os.fdopen(fd, "r+b", buffering=0)
            except Exception:
                os.close(fd)
                raise
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                if self.path.stat().st_size == 0:
                    self._handle.write(b"0")
                    self._handle.flush()
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except LibraryArchiveError:
            self.release()
            raise
        except (OSError, IOError) as exc:
            self.release()
            raise _error(self._busy_message) from exc
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "LibraryOperationLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def _snapshot_database(source: Path, destination: Path) -> None:
    src: sqlite3.Connection | None = None
    dst: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(source)
        dst = sqlite3.connect(destination)
        src.backup(dst)
    except sqlite3.Error as exc:
        raise _error(f"Could not create a consistent SQLite snapshot: {source}") from exc
    finally:
        if src is not None:
            src.close()
        if dst is not None:
            dst.close()
    _validate_database(destination)


def backup_library(
    library_path: Path | str | None = None,
    output_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
) -> Path:
    library = _resolve_library_arg(library_path, create_default=False)
    _assert_active_library(library)
    output = Path(output_path).expanduser().absolute() if output_path is not None else _default_backup_path(library, Path(backup_dir).expanduser().absolute() if backup_dir else None)
    _assert_outside_library(output, library, label="Archive output")

    with LibraryOperationLock(library):
        if os.path.lexists(output):
            raise _error(f"Archive output already exists; choose a new path: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        entries = _iter_payload_files(library)
        total_payload = sum(size for _, _, size, _ in entries)
        try:
            same_device = os.stat(library.parent).st_dev == os.stat(output.parent).st_dev
        except OSError as exc:
            raise _error("Could not compare backup staging and output filesystems") from exc
        cushion = 1024 * 1024
        _require_free_space(
            library.parent,
            total_payload * (2 if same_device else 1) + cushion,
            operation="backup",
        )
        if not same_device:
            _require_free_space(output.parent, total_payload + cushion, operation="backup output")
        ledger = _validate_database(library / "db.sqlite", library=library)
        # Stage the DB snapshot and media files in a sibling temporary directory
        # so the tar stream is internally consistent and never enters library/.
        with tempfile.TemporaryDirectory(prefix=f".{library.name}.archive-", dir=str(library.parent)) as temp_name:
            stage = Path(temp_name)
            staged_entries: list[tuple[str, Path, int, str]] = []
            for relative, source, size, digest in entries:
                staged = stage / Path(*PurePosixPath(relative).parts)
                staged.parent.mkdir(parents=True, exist_ok=True)
                if relative == "db.sqlite":
                    _snapshot_database(source, staged)
                    size, digest = _file_hash(staged)
                else:
                    _stage_file(source, staged, size, digest)
                staged_entries.append((relative, staged, size, digest))
            ledger = _validate_database(stage / "db.sqlite", library=stage)
            manifest = {
                "format": ARCHIVE_FORMAT,
                "format_version": ARCHIVE_VERSION,
                "app_version": config.APP_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "required_storage_roots": list(REQUIRED_STORAGE_ROOTS),
                "migrations": ledger,
                "total_size": sum(size for _, _, size, _ in staged_entries),
                "files": [
                    {"path": f"{LIBRARY_PREFIX}/{relative}", "size": size, "sha256": digest}
                    for relative, _, size, digest in staged_entries
                ],
            }
            manifest_payload = _manifest_bytes(manifest)
            temp_archive = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
            with _claim_archive_output(output):
                try:
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                    archive_fd = os.open(temp_archive, flags, 0o600)
                    with os.fdopen(archive_fd, "wb") as raw:
                        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                                _add_bytes(tar, MANIFEST_NAME, manifest_payload)
                                for relative, staged, size, digest in staged_entries:
                                    _add_file(tar, f"{LIBRARY_PREFIX}/{relative}", staged, size, digest)
                        raw.flush()
                        os.fsync(raw.fileno())
                    os.replace(temp_archive, output)
                    _sync_directory(output.parent)
                except LibraryArchiveError:
                    raise
                except (OSError, tarfile.TarError) as exc:
                    raise _error(f"Could not write archive: {output}") from exc
                finally:
                    try:
                        temp_archive.unlink(missing_ok=True)
                    except OSError:
                        pass
    return output


def _read_archive_members(archive: Path) -> tuple[dict[str, tarfile.TarInfo], bytes]:
    members: dict[str, tarfile.TarInfo] = {}
    folded: dict[str, str] = {}
    ancestor_keys: set[str] = set()
    total = 0
    manifest_data: bytes | None = None
    with ExitStack() as stack:
        try:
            raw = stack.enter_context(archive.open("rb"))
            compressed = stack.enter_context(_TrackedGzipReader(fileobj=raw, mode="rb"))
            tar = stack.enter_context(tarfile.open(fileobj=compressed, mode="r:"))
        except (OSError, tarfile.TarError) as exc:
            raise _error(f"Could not open backup archive: {archive}") from exc
        try:
            all_members = tar.getmembers()
            first_end_block = compressed.last_tar_block
            trailing = compressed.read(tarfile.RECORDSIZE + 1)
        except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
            raise _error("Backup archive has invalid or incomplete gzip data") from exc
        except OSError as exc:
            raise _error(f"Could not read backup archive: {archive}") from exc
        except tarfile.TarError as exc:
            raise _error("Backup archive has invalid tar structure") from exc
        _validate_tar_end(first_end_block, trailing)
        if len(all_members) > MAX_MEMBER_COUNT:
            raise _error("Backup archive exceeds the member-count limit")
        for member in all_members:
            name = member.name
            canonical = _canonical_member(name)
            key = _collision_key(canonical)
            if key in folded:
                raise _error(f"Backup archive contains duplicate/case-colliding member: {member.name}")
            folded[key] = canonical
            if member.issym() or member.islnk() or not member.isfile():
                raise _error(f"Backup archive contains a non-regular member: {member.name}")
            ancestors = canonical.split("/")
            for index in range(1, len(ancestors)):
                ancestor = "/".join(ancestors[:index])
                ancestor_key = _collision_key(ancestor)
                if ancestor_key in folded:
                    raise _error(f"Backup archive contains a file/directory conflict: {member.name}")
                ancestor_keys.add(ancestor_key)
            if key in ancestor_keys:
                raise _error(f"Backup archive contains a file/directory conflict: {member.name}")
            if member.size < 0 or member.size > MAX_FILE_SIZE:
                raise _error(f"Backup archive member exceeds the per-file size limit: {member.name}")
            total += member.size
            if total > MAX_TOTAL_UNCOMPRESSED_SIZE:
                raise _error("Backup archive exceeds the total uncompressed size limit")
            if canonical == MANIFEST_NAME:
                if member.size > MAX_MANIFEST_BYTES:
                    raise _error("Backup manifest exceeds the size limit")
                try:
                    handle = tar.extractfile(member)
                    manifest_data = handle.read(MAX_MANIFEST_BYTES + 1) if handle else b""
                except (OSError, KeyError, tarfile.TarError) as exc:
                    raise _error("Could not read backup manifest") from exc
                if len(manifest_data) > MAX_MANIFEST_BYTES:
                    raise _error("Backup manifest exceeds the size limit")
            elif canonical == MANIFEST_NAME or canonical in members:
                raise _error(f"Backup archive contains duplicate member: {member.name}")
            members[canonical] = member
    if manifest_data is None:
        raise _error("Legacy or invalid archive: manifest.json is required; create a new backup with the current command")
    return members, manifest_data


def _parse_manifest(manifest_data: bytes, members: dict[str, tarfile.TarInfo]) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_data.decode("utf-8"), object_pairs_hook=_json_no_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("Backup manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise _error("Backup manifest must be a JSON object")
    if set(manifest) != MANIFEST_KEYS:
        raise _error("Backup manifest has an invalid top-level schema")
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise _error("Backup manifest has an unsupported format identity")
    version = manifest.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version != ARCHIVE_VERSION:
        raise _error(f"Backup manifest version is unsupported: {version!r}")
    if not isinstance(manifest.get("app_version"), str) or not manifest["app_version"].strip():
        raise _error("Backup manifest app_version is invalid")
    if not isinstance(manifest.get("created_at"), str) or not manifest["created_at"].strip():
        raise _error("Backup manifest created_at is invalid")
    roots = manifest.get("required_storage_roots")
    if roots != list(REQUIRED_STORAGE_ROOTS):
        raise _error("Backup manifest required storage roots do not match this application")
    migrations = manifest.get("migrations")
    if not isinstance(migrations, list) or any(not isinstance(item, str) for item in migrations):
        raise _error("Backup manifest migration ledger is invalid")
    if len(migrations) > len(db.MIGRATIONS) or migrations != db.MIGRATIONS[: len(migrations)]:
        raise _error("Backup manifest migration ledger is not an exact known prefix")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise _error("Backup manifest must contain a non-empty files list")
    if len(files) > MAX_MEMBER_COUNT:
        raise _error("Backup manifest exceeds the member-count limit")
    expected: dict[str, tuple[int, str]] = {}
    folded: set[str] = set()
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise _error("Backup manifest file entry has an invalid schema")
        path = item["path"]
        if not isinstance(path, str) or not path.startswith(f"{LIBRARY_PREFIX}/"):
            raise _error("Backup manifest file path is outside library/")
        relative = _canonical_relative(path.removeprefix(f"{LIBRARY_PREFIX}/"))
        canonical = f"{LIBRARY_PREFIX}/{relative}"
        if _collision_key(canonical) in folded:
            raise _error(f"Backup manifest contains duplicate/case-colliding path: {path}")
        folded.add(_collision_key(canonical))
        size = item["size"]
        digest = item["sha256"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > MAX_FILE_SIZE:
            raise _error(f"Backup manifest has an invalid file size: {path}")
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise _error(f"Backup manifest has an invalid SHA256: {path}")
        total += size
        if total > MAX_TOTAL_UNCOMPRESSED_SIZE:
            raise _error("Backup manifest exceeds the total uncompressed size limit")
        expected[canonical] = (size, digest)
    if not isinstance(manifest.get("total_size"), int) or isinstance(manifest["total_size"], bool) or manifest["total_size"] != total:
        raise _error("Backup manifest total_size does not match its file entries")
    if "library/db.sqlite" not in expected:
        raise _error("Backup manifest is missing the required library/db.sqlite payload")
    actual_files = {name for name, member in members.items() if name.startswith("library/") and member.isfile()}
    if actual_files != set(expected):
        raise _error("Backup archive files do not exactly match manifest files")
    extras = {
        name
        for name, member in members.items()
        if member.isfile() and name not in expected and name != MANIFEST_NAME
    }
    if extras:
        raise _error(f"Backup archive contains files not listed in manifest: {sorted(extras)[0]}")
    return manifest


def _extract_and_validate(archive: Path, stage_library: Path) -> dict[str, Any]:
    members, manifest_data = _read_archive_members(archive)
    manifest = _parse_manifest(manifest_data, members)
    _require_free_space(
        stage_library.parent,
        int(manifest["total_size"]) + 1024 * 1024,
        operation="backup verification",
    )
    expected = {
        entry["path"]: (entry["size"], entry["sha256"])
        for entry in manifest["files"]
    }
    stage_library.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        with tarfile.open(archive, mode="r:gz") as tar:
            for name, member in sorted(members.items()):
                if name == MANIFEST_NAME or not member.isfile():
                    continue
                size, expected_hash = expected[name]
                relative = name.removeprefix(f"{LIBRARY_PREFIX}/")
                destination = stage_library / Path(*PurePosixPath(relative).parts)
                if not _within(destination, stage_library):
                    raise _error("Backup archive member escapes staging")
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                try:
                    source = tar.extractfile(member)
                except (OSError, KeyError, tarfile.TarError) as exc:
                    raise _error(f"Could not read backup archive member: {name}") from exc
                if source is None:
                    raise _error(f"Could not read backup archive member: {name}")
                digest = hashlib.sha256()
                written = 0
                try:
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                    destination_fd = os.open(destination, flags, 0o600)
                    with os.fdopen(destination_fd, "wb") as handle:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > MAX_FILE_SIZE:
                                raise _error(f"Backup archive member exceeds the per-file size limit: {name}")
                            digest.update(chunk)
                            handle.write(chunk)
                except LibraryArchiveError:
                    raise
                except (OSError, tarfile.TarError) as exc:
                    raise _error(f"Could not extract backup archive member: {name}") from exc
                if written != size or digest.hexdigest() != expected_hash:
                    raise _error(f"Backup archive checksum/size mismatch: {name}")
            payload_end = max(
                member.offset_data
                + ((member.size + tarfile.BLOCKSIZE - 1) // tarfile.BLOCKSIZE) * tarfile.BLOCKSIZE
                for member in members.values()
            )
            try:
                tar.fileobj.seek(payload_end)
                complete_tail = tar.fileobj.read(tarfile.BLOCKSIZE + tarfile.RECORDSIZE + 1)
            except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
                raise _error("Backup archive has invalid or incomplete gzip data") from exc
            except OSError as exc:
                raise _error(f"Could not read backup archive: {archive}") from exc
            _validate_tar_end(complete_tail[: tarfile.BLOCKSIZE], complete_tail[tarfile.BLOCKSIZE :])
        for root_name in REQUIRED_STORAGE_ROOTS:
            root = stage_library / root_name
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            _assert_directory(root, label=f"Staged storage root {root_name}")
        _assert_active_library(stage_library)
        ledger = _validate_database(stage_library / "db.sqlite", library=stage_library)
        if ledger != manifest["migrations"]:
            raise _error("Backup manifest migration ledger does not match the staged database")
        return manifest
    except Exception:
        raise


def _verify_to_temp(archive: Path, temp_parent: Path) -> tuple[dict[str, Any], Path]:
    stage_library = temp_parent / "library"
    manifest = _extract_and_validate(archive, stage_library)
    return manifest, stage_library


def verify_backup(archive_path: Path | str, library_path: Path | str | None = None) -> dict[str, Any]:
    archive = Path(archive_path).expanduser().absolute()
    if not archive.is_file() or _is_reparse_or_link(archive):
        raise _error(f"Backup archive does not exist or is unsafe: {archive}")
    library = _resolve_library_arg(library_path) if library_path is not None else None
    if library is not None:
        _assert_outside_library(archive, library, label="Backup archive")
    with tempfile.TemporaryDirectory(prefix=".library-archive-verify-") as temp_name:
        manifest, _ = _verify_to_temp(archive, Path(temp_name))
    return manifest


def restore_library(
    archive_path: Path | str,
    library_path: Path | str | None = None,
    *,
    confirm: bool = False,
) -> Path:
    global LAST_PRESERVED_PATH
    LAST_PRESERVED_PATH = None
    if not confirm:
        raise _error("Restore publishes the archived library at the active path; pass --yes to confirm")
    archive = Path(archive_path).expanduser().absolute()
    if not archive.is_file() or _is_reparse_or_link(archive):
        raise _error(f"Backup archive does not exist or is unsafe: {archive}")
    library = _resolve_library_arg(library_path, create_default=False)
    _assert_active_library(library, must_exist=False)
    _assert_outside_library(archive, library, label="Backup archive")
    with LibraryOperationLock(library):
        active_exists = _assert_active_library(library, must_exist=False)
        preflight_members, preflight_data = _read_archive_members(archive)
        preflight_manifest = _parse_manifest(preflight_data, preflight_members)
        required_space = int(preflight_manifest["total_size"]) + 1024 * 1024
        _require_free_space(library.parent, required_space, operation="restore")
        with tempfile.TemporaryDirectory(prefix=f".{library.name}.restore-", dir=str(library.parent)) as temp_name:
            manifest, stage_library = _verify_to_temp(archive, Path(temp_name))
            ledger = manifest["migrations"]
            if len(ledger) < len(db.MIGRATIONS):
                try:
                    db.init_db(stage_library)
                except (OSError, sqlite3.Error, ValueError) as exc:
                    raise _error("Could not upgrade the restored database using known migrations") from exc
                for root_name in REQUIRED_STORAGE_ROOTS:
                    (stage_library / root_name).mkdir(parents=True, exist_ok=True)
                upgraded_ledger = _validate_database(stage_library / "db.sqlite", library=stage_library)
                if upgraded_ledger != db.MIGRATIONS:
                    raise _error("Restored database did not reach the current known migration ledger")
            final_ledger = _validate_database(stage_library / "db.sqlite", library=stage_library)
            if final_ledger != db.MIGRATIONS:
                raise _error("Restored database migration ledger is not current")
            if _assert_active_library(library, must_exist=False) != active_exists:
                raise _error("Active library appeared or disappeared during restore; nothing was replaced")
            preserve = (
                library.parent
                / f".{library.name}.pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
                if active_exists
                else None
            )
            if preserve is not None and os.path.lexists(preserve):
                raise _error(f"Restore preservation path already exists: {preserve}")
            published = False
            try:
                # sqlite3.Connection's context manager commits but does not
                # close the handle; collect short-lived fixture/app setup
                # connections before Windows directory replacement.
                gc.collect()
                if preserve is not None:
                    os.replace(library, preserve)
                    _sync_directory(library.parent)
                os.replace(stage_library, library)
                _sync_directory(library.parent)
                published = True
                LAST_PRESERVED_PATH = preserve
            except OSError as exc:
                rollback_error: OSError | None = None
                if preserve is not None and preserve.exists() and not library.exists():
                    try:
                        os.replace(preserve, library)
                        _sync_directory(library.parent)
                    except OSError as rollback_exc:
                        rollback_error = rollback_exc
                if rollback_error is not None:
                    raise _error(
                        f"Could not publish restored library ({exc}); automatic rollback also failed "
                        f"({rollback_error}). The original remains at: {preserve}"
                    ) from exc
                if preserve is not None:
                    raise _error(f"Could not publish restored library ({exc}); the active library was rolled back") from exc
                raise _error(f"Could not publish restored library ({exc}); the active path remains empty") from exc
            if not published:
                raise _error("Restore did not publish a library")
    return library


# Short aliases make the service convenient for app integration without
# exposing implementation-specific helpers.
backup = backup_library
verify = verify_backup
restore = restore_library


__all__ = [
    "ARCHIVE_FORMAT",
    "ARCHIVE_VERSION",
    "LibraryArchiveError",
    "LibraryOperationLock",
    "backup_library",
    "verify_backup",
    "restore_library",
    "backup",
    "verify",
    "restore",
]
