from __future__ import annotations

import io
import json
import os
import sqlite3
import stat
import tarfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.services import library_archives
from backend.services.library_archives import (
    LibraryArchiveError,
    LibraryOperationLock,
    backup_library,
    restore_library,
    verify_backup,
)


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    db.init_db(library)
    for root in ("originals", "thumbs", "previews", "generation-results", "generation-references"):
        (library / root / "nested").mkdir(parents=True, exist_ok=True)
        (library / root / "nested" / f"{root}.bin").write_bytes(root.encode())
    return library


def _members(path: Path) -> list[str]:
    with tarfile.open(path, "r:gz") as tar:
        return tar.getnames()


def _rewrite_archive(
    source: Path,
    destination: Path,
    *,
    manifest_update=None,
    omit: set[str] | None = None,
    replace: dict[str, bytes] | None = None,
    extra: dict[str, bytes] | None = None,
) -> Path:
    omit = omit or set()
    replace = replace or {}
    extra = extra or {}
    with tarfile.open(source, "r:gz") as archive:
        payloads = {
            member.name: archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile() and member.name not in omit
        }
    manifest = json.loads(payloads["manifest.json"])
    if manifest_update is not None:
        manifest_update(manifest)
    payloads["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    payloads.update(replace)
    payloads.update(extra)
    with tarfile.open(destination, "w:gz") as archive:
        for name, payload in payloads.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return destination


def _init_migration_prefix(library: Path, migrations: list[str]) -> None:
    library.mkdir()
    for root in ("originals", "thumbs", "previews", "generation-results", "generation-references"):
        (library / root).mkdir()
    conn = sqlite3.connect(library / "db.sqlite")
    try:
        conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in migrations:
            sql = (Path(db.__file__).parent / "migrations" / migration).read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                (migration,),
            )
            conn.commit()
    finally:
        conn.close()


def test_backup_verify_restore_round_trip_and_preserves_original(tmp_path, monkeypatch):
    library = _library(tmp_path)
    outside = tmp_path / "state"
    outside.mkdir()
    (outside / "auth.json").write_text("credential-canary", encoding="utf-8")
    (outside / "config.json").write_text("config-canary", encoding="utf-8")
    (outside / "session.json").write_text("session-canary", encoding="utf-8")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(outside / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(outside / "config.json"))
    archive = backup_library(library, tmp_path / "backup.tar.gz")

    manifest = verify_backup(archive, library)
    assert {Path(item["path"]).parts[1] for item in manifest["files"]} == {
        "db.sqlite",
        "originals",
        "thumbs",
        "previews",
        "generation-results",
        "generation-references",
    }
    assert "manifest.json" in _members(archive)
    assert all(not name.startswith("state/") for name in _members(archive))
    with tarfile.open(archive, "r:gz") as packaged:
        archive_bytes = b"".join(
            packaged.extractfile(member).read()
            for member in packaged.getmembers()
            if member.isfile()
        )
    for canary in (b"credential-canary", b"config-canary", b"session-canary"):
        assert canary not in archive_bytes

    (library / "originals" / "nested" / "originals.bin").write_text("active", encoding="utf-8")
    restore_library(archive, library, confirm=True)
    assert (library / "originals" / "nested" / "originals.bin").read_bytes() == b"originals"
    assert list(tmp_path.glob(".library.pre-restore-*")), "the replaced library must be preserved"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not meaningful on Windows")
def test_backup_archive_is_private_to_its_owner(tmp_path):
    library = _library(tmp_path)

    archive = backup_library(library, tmp_path / "backup.tar.gz")

    assert stat.S_IMODE(archive.stat().st_mode) == 0o600


def test_corruption_and_legacy_archive_are_rejected(tmp_path):
    library = _library(tmp_path)
    archive = backup_library(library, tmp_path / "backup.tar.gz")
    corrupted = tmp_path / "corrupt.tar.gz"
    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0xFF
    corrupted.write_bytes(data)
    with pytest.raises(LibraryArchiveError):
        verify_backup(corrupted)

    legacy = tmp_path / "legacy.tar.gz"
    with tarfile.open(legacy, "w:gz") as tar:
        info = tarfile.TarInfo("db.sqlite")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(LibraryArchiveError, match="manifest.json"):
        verify_backup(legacy)


def test_lock_is_nonblocking(tmp_path):
    library = _library(tmp_path)
    first = LibraryOperationLock(library).acquire()
    try:
        with pytest.raises(LibraryArchiveError, match="busy"):
            LibraryOperationLock(library).acquire()
    finally:
        first.release()


def test_lock_rejects_symlink_without_touching_target(tmp_path):
    library = _library(tmp_path)
    target = tmp_path / "outside-lock-target"
    target.write_bytes(b"")
    lock_path = tmp_path / ".library.library-operation.lock"
    try:
        lock_path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc}")

    with pytest.raises(LibraryArchiveError, match="lock path is unsafe"):
        LibraryOperationLock(library).acquire()

    assert target.read_bytes() == b""


def test_running_app_holds_the_same_library_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_PATH", str(tmp_path / "module-default-library"))
    from backend.main import create_app

    library = _library(tmp_path)
    output = tmp_path / "while-running.tar.gz"
    with TestClient(create_app(library_path=library)) as client:
        assert client.get("/api/health").status_code == 200
        with pytest.raises(LibraryArchiveError, match="running app"):
            backup_library(library, output)
    assert backup_library(library, output) == output


def test_sqlite_wal_content_is_snapshotted_without_sidecars(tmp_path):
    library = _library(tmp_path)
    connection = sqlite3.connect(library / "db.sqlite")
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE backup_wal_probe(value TEXT NOT NULL)")
        connection.execute("INSERT INTO backup_wal_probe(value) VALUES ('committed-in-wal')")
        connection.commit()
        archive = backup_library(library, tmp_path / "wal.tar.gz")
    finally:
        connection.close()

    names = _members(archive)
    assert "library/db.sqlite-wal" not in names
    assert "library/db.sqlite-shm" not in names
    restored_db = tmp_path / "snapshot.sqlite"
    with tarfile.open(archive, "r:gz") as packaged:
        restored_db.write_bytes(packaged.extractfile("library/db.sqlite").read())
    with sqlite3.connect(restored_db) as snapshot:
        assert snapshot.execute("SELECT value FROM backup_wal_probe").fetchone()[0] == "committed-in-wal"


def test_backup_rejects_source_replaced_by_symlink_after_enumeration(tmp_path, monkeypatch):
    library = _library(tmp_path)
    victim = library / "originals" / "nested" / "originals.bin"
    outside = tmp_path / "outside-secret"
    outside.write_bytes(b"private-outside-canary")
    real_iter_payload = library_archives._iter_payload_files

    def enumerate_then_swap(path):
        entries = real_iter_payload(path)
        victim.unlink()
        try:
            victim.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"file symlinks are unavailable: {exc}")
        return entries

    monkeypatch.setattr(library_archives, "_iter_payload_files", enumerate_then_swap)
    output = tmp_path / "must-not-leak.tar.gz"
    with pytest.raises(LibraryArchiveError, match="symlink|changed"):
        backup_library(library, output)
    assert not output.exists()


def test_backup_rejects_hardlinked_source_file(tmp_path):
    library = _library(tmp_path)
    outside = tmp_path / "outside-hardlink-source"
    outside.write_bytes(b"outside")
    linked = library / "originals" / "hard-linked.bin"
    try:
        os.link(outside, linked)
    except OSError as exc:
        pytest.skip(f"hard links are unavailable: {exc}")

    with pytest.raises(LibraryArchiveError, match="private regular file"):
        backup_library(library, tmp_path / "hardlink.tar.gz")


def test_archive_inside_library_and_unknown_migration_are_rejected(tmp_path):
    library = _library(tmp_path)
    with pytest.raises(LibraryArchiveError, match="outside"):
        backup_library(library, library / "inside.tar.gz")

    conn = db.connect(library)
    try:
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", ("999_future.sql", "now"))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(LibraryArchiveError, match="known prefix"):
        backup_library(library, tmp_path / "future.tar.gz")


def test_backup_rejects_migration_ledger_that_does_not_match_schema(tmp_path):
    library = _library(tmp_path)
    with db.connect(library) as connection:
        connection.execute("DROP TABLE images")
        connection.commit()

    with pytest.raises(LibraryArchiveError, match="missing required table: images"):
        backup_library(library, tmp_path / "inconsistent-schema.tar.gz")


def test_backup_rejects_view_substituted_for_required_table(tmp_path):
    library = _library(tmp_path)
    with db.connect(library) as connection:
        connection.execute("ALTER TABLE items RENAME TO items_base")
        connection.execute("CREATE VIEW items AS SELECT * FROM items_base WHERE 0")
        connection.commit()

    with pytest.raises(LibraryArchiveError, match="missing required table: items"):
        backup_library(library, tmp_path / "view-schema.tar.gz")


def test_manifest_paths_are_canonical(tmp_path):
    library = _library(tmp_path)
    archive = backup_library(library, tmp_path / "backup.tar.gz")
    with tarfile.open(archive, "r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read())
    paths = [entry["path"] for entry in manifest["files"]]
    assert paths == sorted(paths)
    assert all(path == path.replace("\\", "/") and ".." not in Path(path).parts for path in paths)


def test_existing_output_unsafe_member_and_failed_restore_leave_state_unchanged(tmp_path):
    library = _library(tmp_path)
    archive = backup_library(library, tmp_path / "backup.tar.gz")
    with pytest.raises(LibraryArchiveError, match="already exists"):
        backup_library(library, archive)

    unsafe = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe, "w:gz") as tar:
        info = tarfile.TarInfo("library/../outside")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(LibraryArchiveError, match="traversal"):
        verify_backup(unsafe)

    duplicate_json = tmp_path / "duplicate-json.tar.gz"
    payload = b'{"format":"image-prompt-library","format":"image-prompt-library"}'
    with tarfile.open(duplicate_json, "w:gz") as tar:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(LibraryArchiveError, match="duplicate JSON key"):
        verify_backup(duplicate_json)

    sentinel = library / "originals" / "nested" / "originals.bin"
    before = sentinel.read_bytes()
    corrupted = tmp_path / "corrupt-restore.tar.gz"
    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0xFF
    corrupted.write_bytes(data)
    with pytest.raises(LibraryArchiveError):
        restore_library(corrupted, library, confirm=True)
    assert sentinel.read_bytes() == before


def test_two_libraries_cannot_publish_to_the_same_output_concurrently(tmp_path, monkeypatch):
    first_library = _library(tmp_path / "first")
    second_library = _library(tmp_path / "second")
    output = tmp_path / "shared-output.tar.gz"
    entered = threading.Event()
    release = threading.Event()
    failures: list[BaseException] = []
    real_add_file = library_archives._add_file

    def slow_add_file(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return real_add_file(*args, **kwargs)

    def create_first_backup():
        try:
            backup_library(first_library, output)
        except BaseException as exc:  # captured for assertion in the test thread
            failures.append(exc)

    monkeypatch.setattr(library_archives, "_add_file", slow_add_file)
    worker = threading.Thread(target=create_first_backup)
    worker.start()
    assert entered.wait(timeout=10)
    try:
        with pytest.raises(LibraryArchiveError, match="already being created"):
            backup_library(second_library, output)
    finally:
        release.set()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert not failures
    assert verify_backup(output)["format"] == "image-prompt-library"


@pytest.mark.parametrize(
    "unsafe_name",
    (
        "/absolute",
        "C:/drive-qualified",
        "//server/share/unc",
        "../escaped",
        "library\\originals\\backslash",
        "library/originals/CON.txt",
        "library/originals/trailing-dot.",
        "library/originals/trailing-space ",
        "library/originals/control\x01.txt",
    ),
)
def test_unsafe_cross_platform_member_names_are_rejected(tmp_path, unsafe_name):
    archive = tmp_path / "unsafe-member.tar.gz"
    with tarfile.open(archive, "w:gz") as packaged:
        info = tarfile.TarInfo(unsafe_name)
        info.size = 1
        packaged.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(LibraryArchiveError):
        verify_backup(archive)


@pytest.mark.parametrize("member_type", (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.DIRTYPE))
def test_link_and_special_archive_members_are_rejected(tmp_path, member_type):
    archive = tmp_path / "special-member.tar.gz"
    with tarfile.open(archive, "w:gz") as packaged:
        info = tarfile.TarInfo("library/originals/unsafe")
        info.type = member_type
        info.linkname = "manifest.json"
        packaged.addfile(info)
    with pytest.raises(LibraryArchiveError, match="non-regular"):
        verify_backup(archive)


def test_case_unicode_and_file_directory_conflicts_are_rejected(tmp_path):
    cases = (
        ("library/originals/Foo.txt", "library/originals/foo.TXT"),
        ("library/originals/\u00e9.txt", "library/originals/e\u0301.txt"),
        ("library/originals/file", "library/originals/file/child"),
    )
    for index, names in enumerate(cases):
        archive = tmp_path / f"conflict-{index}.tar.gz"
        with tarfile.open(archive, "w:gz") as packaged:
            for name in names:
                info = tarfile.TarInfo(name)
                info.size = 1
                packaged.addfile(info, io.BytesIO(b"x"))
        with pytest.raises(LibraryArchiveError):
            verify_backup(archive)


def test_manifest_identity_extra_member_and_checksum_are_rejected(tmp_path):
    library = _library(tmp_path)
    archive = backup_library(library, tmp_path / "valid.tar.gz")

    wrong_identity = _rewrite_archive(
        archive,
        tmp_path / "wrong-identity.tar.gz",
        manifest_update=lambda manifest: manifest.update(format="another-product"),
    )
    with pytest.raises(LibraryArchiveError, match="format identity"):
        verify_backup(wrong_identity)

    extra_manifest_field = _rewrite_archive(
        archive,
        tmp_path / "extra-manifest-field.tar.gz",
        manifest_update=lambda manifest: manifest.update(unexpected="not-version-one"),
    )
    with pytest.raises(LibraryArchiveError, match="top-level schema"):
        verify_backup(extra_manifest_field)

    extra = _rewrite_archive(
        archive,
        tmp_path / "extra.tar.gz",
        extra={"library/originals/extra.txt": b"extra"},
    )
    with pytest.raises(LibraryArchiveError, match="exactly match"):
        verify_backup(extra)

    changed = _rewrite_archive(
        archive,
        tmp_path / "changed.tar.gz",
        replace={"library/originals/nested/originals.bin": b"changed"},
    )
    with pytest.raises(LibraryArchiveError, match="checksum/size mismatch"):
        verify_backup(changed)


def test_restore_rejects_missing_database_media_reference_before_mutation(tmp_path):
    source = _library(tmp_path / "source")
    referenced = source / "originals" / "referenced.bin"
    referenced.write_bytes(b"referenced")
    with db.connect(source) as connection:
        connection.execute(
            "INSERT INTO items(id,title,slug,created_at,updated_at) VALUES ('item','Item','item','now','now')"
        )
        connection.execute(
            "INSERT INTO images(id,item_id,original_path,created_at) VALUES ('image','item','originals/referenced.bin','now')"
        )
        connection.commit()
    archive = backup_library(source, tmp_path / "referenced.tar.gz")

    def omit_reference(manifest):
        manifest["files"] = [
            entry for entry in manifest["files"] if entry["path"] != "library/originals/referenced.bin"
        ]
        manifest["total_size"] = sum(entry["size"] for entry in manifest["files"])

    broken = _rewrite_archive(
        archive,
        tmp_path / "missing-reference.tar.gz",
        manifest_update=omit_reference,
        omit={"library/originals/referenced.bin"},
    )
    active = _library(tmp_path / "active")
    sentinel = active / "originals" / "nested" / "originals.bin"
    before = sentinel.read_bytes()
    with pytest.raises(LibraryArchiveError, match="missing or unsafe"):
        restore_library(broken, active, confirm=True)
    assert sentinel.read_bytes() == before


def test_backup_rejects_empty_mandatory_original_path(tmp_path):
    library = _library(tmp_path)
    with db.connect(library) as connection:
        connection.execute(
            "INSERT INTO items(id,title,slug,created_at,updated_at) VALUES ('item','Item','item','now','now')"
        )
        connection.execute(
            "INSERT INTO images(id,item_id,original_path,created_at) VALUES ('image','item','','now')"
        )
        connection.commit()

    with pytest.raises(LibraryArchiveError, match="original_path must reference"):
        backup_library(library, tmp_path / "invalid.tar.gz")


def test_restore_can_publish_to_a_missing_fresh_library_path(tmp_path):
    source = _library(tmp_path / "source")
    archive = backup_library(source, tmp_path / "fresh.tar.gz")
    destination = tmp_path / "fresh-install" / "library"

    restore_library(archive, destination, confirm=True)

    assert (destination / "originals" / "nested" / "originals.bin").read_bytes() == b"originals"
    assert library_archives.LAST_PRESERVED_PATH is None


def test_known_older_schema_is_migrated_only_in_staging(tmp_path):
    old_library = tmp_path / "old-library"
    _init_migration_prefix(old_library, db.MIGRATIONS[:-1])
    archive = backup_library(old_library, tmp_path / "old-schema.tar.gz")
    active = _library(tmp_path / "active")

    restore_library(archive, active, confirm=True)

    with db.connect(active) as connection:
        ledger = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY rowid")]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert ledger == db.MIGRATIONS
    assert {"generation_sets", "provider_queue_states"}.issubset(tables)
    with db.connect(old_library) as connection:
        assert connection.execute("SELECT version FROM schema_migrations ORDER BY rowid").fetchall()[-1][0] == db.MIGRATIONS[-2]


def test_handled_publish_failure_rolls_active_library_back(tmp_path, monkeypatch):
    source = _library(tmp_path / "source")
    archive = backup_library(source, tmp_path / "valid.tar.gz")
    active = _library(tmp_path / "active")
    sentinel = active / "originals" / "nested" / "originals.bin"
    sentinel.write_bytes(b"active-before-failure")
    real_replace = library_archives.os.replace
    calls = 0

    def fail_second_replace(source_path, destination_path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publish failure")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(library_archives.os, "replace", fail_second_replace)
    with pytest.raises(LibraryArchiveError, match="rolled back"):
        restore_library(archive, active, confirm=True)
    assert sentinel.read_bytes() == b"active-before-failure"


def test_backup_failure_does_not_publish_partial_archive(tmp_path, monkeypatch):
    library = _library(tmp_path)
    output = tmp_path / "should-not-exist.tar.gz"

    def fail_archive_file(*args, **kwargs):
        raise OSError("injected archive failure")

    monkeypatch.setattr(library_archives, "_add_file", fail_archive_file)
    with pytest.raises(LibraryArchiveError, match="Could not write archive"):
        backup_library(library, output)
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))
    assert not list(tmp_path.glob(f".{output.name}.claim"))


def test_library_archive_error_cleans_private_partial_archive(tmp_path, monkeypatch):
    library = _library(tmp_path)
    output = tmp_path / "changed-source.tar.gz"

    def fail_archive_file(*args, **kwargs):
        raise LibraryArchiveError("Library file changed during backup")

    monkeypatch.setattr(library_archives, "_add_file", fail_archive_file)
    with pytest.raises(LibraryArchiveError, match="changed during backup"):
        backup_library(library, output)
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))
    assert not list(tmp_path.glob(f".{output.name}.claim"))


def test_backup_fails_closed_when_disk_space_cannot_be_checked(tmp_path, monkeypatch):
    library = _library(tmp_path)
    output = tmp_path / "unchecked-space.tar.gz"

    def fail_disk_usage(*args, **kwargs):
        raise OSError("injected disk usage failure")

    monkeypatch.setattr(library_archives.shutil, "disk_usage", fail_disk_usage)
    with pytest.raises(LibraryArchiveError, match="determine free disk space"):
        backup_library(library, output)
    assert not output.exists()


def test_verify_fails_before_extraction_when_temp_space_is_insufficient(tmp_path, monkeypatch):
    library = _library(tmp_path)
    archive = backup_library(library, tmp_path / "space-check.tar.gz")
    monkeypatch.setattr(
        library_archives.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=1, used=1, free=0),
    )

    with pytest.raises(LibraryArchiveError, match="Insufficient disk space"):
        verify_backup(archive)


def test_sqlite_open_failure_is_reported_without_raw_traceback(tmp_path, monkeypatch):
    library = _library(tmp_path)

    def fail_connect(*args, **kwargs):
        raise sqlite3.OperationalError("injected SQLite open failure")

    monkeypatch.setattr(library_archives.sqlite3, "connect", fail_connect)
    with pytest.raises(LibraryArchiveError, match="Could not validate SQLite database"):
        backup_library(library, tmp_path / "sqlite-failure.tar.gz")
