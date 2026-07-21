# Backup and Restore

Image Prompt Library is local-first. The active library contains the SQLite database and library-managed media; app-owned OAuth credentials, provider configuration, and local device-login/session state live outside it.

## Before backup or restore

Stop the app first. Backup and restore share a library operation lock with the running app, so the command fails closed if another app, backup, or restore process is using that library.

- Windows: `image-prompt-library stop`
- macOS service: `image-prompt-library service stop`
- Foreground macOS/Linux: press `Ctrl-C` in the terminal that is running the app

The commands do not automatically stop or restart the app because doing so could interrupt generation work without consent.

## Supported commands

Create a timestamped archive in the configured `BACKUP_DIR`:

```bash
image-prompt-library backup
```

Choose an exact path outside the active library:

```bash
image-prompt-library backup --output /safe/place/image-prompt-library-backup.tar.gz
```

Validate an archive without changing the active library:

```bash
image-prompt-library verify-backup /safe/place/image-prompt-library-backup.tar.gz
```

Restore after verification:

```bash
image-prompt-library restore /safe/place/image-prompt-library-backup.tar.gz --yes
```

Source checkouts may continue to use `./scripts/backup.sh`; it is now a compatibility wrapper around the same portable backup engine.

## Portable archive contract

The `.tar.gz` archive has a fixed, versioned layout:

- `manifest.json`
- `library/db.sqlite`
- `library/originals/**`
- `library/thumbs/**`
- `library/previews/**`
- `library/generation-results/**`
- `library/generation-references/**`

The manifest records the archive format version, app version, required storage roots, SQLite migration ledger, and every file's relative path, size, and SHA-256. Paths never contain the local library location, machine username, or hostname. Empty storage roots are recreated during restore.

SHA-256 detects accidental corruption; it is not a signature. Someone who can deliberately rewrite an archive can also rewrite its manifest.

Backup uses SQLite's snapshot API rather than copying a potentially live `db.sqlite` byte-for-byte. It validates SQLite integrity, foreign keys, migrations, library-owned media references, paths, links, file types, and size limits before publishing the archive. A handled write or validation failure never publishes a partial archive under the requested final name. On POSIX, both the in-progress and final archive are created owner-only (`0600`); on Windows, choose a backup directory whose ACL is private to the intended account.

## Safe restore behavior

Restore validates the complete archive and extracts it into a fresh sibling staging directory before touching the active library. Validation reads the gzip stream through its CRC and size trailer, so truncated or container-corrupt archives fail before restore. It also rejects unsupported format versions, old manifest-less archives, checksum mismatches, unknown or divergent database migrations, absolute or traversing paths, links, special files, duplicate/case-conflicting names, extra payload files, and missing referenced media.

If the archived database is an older known migration prefix, only the staged copy is migrated. The active library remains unchanged if validation or migration fails.

After successful validation, restore over an existing library:

1. renames the current library to a sibling named like `.ImagePromptLibrary.pre-restore-<timestamp>-<id>`;
2. renames the staged library into the configured active path; and
3. leaves the preserved pre-restore library in place for manual removal after review.

If the second rename fails during a handled error, restore attempts to put the preserved original back. A sudden power loss between the two directory renames cannot be made transactionally atomic across every filesystem; the preserved original and staging paths are therefore never silently deleted.

On a fresh machine, restore may publish directly to a configured active-library path that does not exist yet. There is no previous library to preserve in that case. Its parent directory must be writable, and the same credential-path boundary still applies.

Full abrupt power-loss reconciliation is not part of this release. If the machine loses power during the final directory switch and the active path is missing afterward, do not start adding new items: inspect the sibling `.pre-restore-*` and `.restore-*` directories, keep both, and restore the original path manually before retrying. Normal handled failures perform automatic rollback.

Archives made by the former `backup.sh` format have no manifest, use machine-dependent paths, and omit generation storage. They are deliberately rejected rather than guessed at. Keep them for manual recovery, or open the old library with the current app stopped and create a new portable backup.

## Privacy boundary

OAuth tokens, provider config, device-login/session state, logs, installer state, and `BACKUP_DIR` are outside the payload allowlist and are not traversed. The same credential-path boundary used at app startup rejects `IMAGE_PROMPT_LIBRARY_AUTH_PATH` or `IMAGE_PROMPT_LIBRARY_CONFIG_PATH` if either resolves inside the active library.

This is an allowlist, not a content scrubber. Prompts, notes, generation history, provenance, imported source paths, and other values deliberately stored in `db.sqlite` remain in the private recovery archive. Do not put secrets in library content, do not publish backup archives, and keep them outside both the repository and active library.

There is no in-app Restore button in this milestone: replacing the database from the process that owns it would undermine the offline safety boundary. Cloud backup, cloud sync, accounts, arbitrary archive import, library merging, scheduling, encryption, and incremental backup remain out of scope.
