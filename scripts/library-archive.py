"""Command-line portable backup/verify/restore for the Image Prompt Library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Running from a source checkout or a packaged app root should both import the
# bundled backend without requiring the caller to set PYTHONPATH.
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from backend.services import library_archives as archive_service  # noqa: E402
from backend.services.library_archives import (  # noqa: E402
    LibraryArchiveError,
    backup_library,
    restore_library,
    verify_backup,
)


def _common_library(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--library", type=Path, help="active library directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="library-archive", description="Portable Image Prompt Library backup tools")
    commands = parser.add_subparsers(dest="command", required=True)

    backup = commands.add_parser("backup", help="create a portable .tar.gz backup")
    _common_library(backup)
    backup.add_argument("--output", type=Path, help="archive path (outside the active library)")
    backup.add_argument("--backup-dir", type=Path, help="directory for a timestamped archive")

    verify = commands.add_parser("verify-backup", help="validate archive structure, hashes, and SQLite")
    verify.add_argument("archive", type=Path)
    _common_library(verify)

    restore = commands.add_parser("restore", help="replace the active library from an archive")
    restore.add_argument("archive", type=Path)
    _common_library(restore)
    restore.add_argument("--yes", action="store_true", help="confirm replacement of the active library")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "backup":
            path = backup_library(args.library, args.output, args.backup_dir)
            print(f"Backup created: {path}")
        elif args.command == "verify-backup":
            manifest = verify_backup(args.archive, args.library)
            print(
                f"Backup verified: {args.archive} "
                f"({len(manifest.get('files', []))} files, app {manifest.get('app_version', 'unknown')})"
            )
        elif args.command == "restore":
            path = restore_library(args.archive, args.library, confirm=args.yes)
            print(f"Restore completed; active library: {path}")
            if archive_service.LAST_PRESERVED_PATH is not None:
                print(f"Previous library preserved: {archive_service.LAST_PRESERVED_PATH}")
        else:  # argparse enforces this, but keep the return distinct if extended.
            print("Unknown archive command", file=sys.stderr)
            return 2
        return 0
    except (LibraryArchiveError, OSError, ValueError) as exc:
        print(f"library-archive error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
