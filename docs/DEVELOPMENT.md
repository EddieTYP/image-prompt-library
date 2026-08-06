# Development Guide

Use this path if you want to develop the app, inspect unreleased `main`, or run from a checkout.

## Source setup

```bash
git clone https://github.com/EddieTYP/image-prompt-library.git
cd image-prompt-library
./scripts/setup.sh
./scripts/start.sh
```

Open <http://127.0.0.1:8000/>.

`setup.sh` auto-detects `python3.13`, `python3.12`, `python3.11`, or `python3.10` before falling back to `python3`. On macOS, `/usr/bin/python3` may still be Python 3.9; if setup cannot find a new enough interpreter, install Python 3.10+ and rerun with an explicit interpreter:

```bash
PYTHON=/path/to/python3.12 ./scripts/setup.sh
./scripts/start.sh
```

`start.sh` uses `.venv/bin/python` from setup when available and prints an actionable setup message if Python dependencies are missing.

`scripts/start.sh` builds the frontend and serves the built app through FastAPI, so source local use only needs one server after setup.

## Development mode

For frontend/backend development with Vite hot reload:

```bash
./scripts/dev.sh
```

Open <http://127.0.0.1:5177/>.

Default development ports:

- Backend API: <http://127.0.0.1:8000>
- Vite frontend: <http://127.0.0.1:5177>

## Configuration

Copy `.env.example` to `.env` and edit if needed:

```bash
cp .env.example .env
```

The POSIX scripts read supported `.env` entries as literal `KEY=value` data; they do not execute shell syntax or expand quotes, variables, or command substitutions. Write paths and values directly, including spaces when needed.

Important settings:

```bash
IMAGE_PROMPT_LIBRARY_PATH=./library
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=5177
BACKUP_DIR=./backups
```

`IMAGE_PROMPT_LIBRARY_PATH` controls where your private database and images live. The default `./library` is repo-local and intentionally ignored by git. For long-term personal use, you may prefer a durable path such as `~/ImagePromptLibrary`.

## Data layout

Runtime data lives under `IMAGE_PROMPT_LIBRARY_PATH`:

```text
library/db.sqlite       SQLite metadata and full-text search index
library/originals/      original uploaded/imported images
library/previews/       generated preview images
library/thumbs/         generated thumbnail images
library/generation-results/       generated results awaiting or retaining review
library/generation-references/    library-owned copies used by generation jobs
```

Do not commit runtime `library/` data to git. It is your private prompt/image collection.

## Add your own prompts and images

1. Start the app.
2. Click `+ Add`.
3. Add a title, prompt text, collection, optional tags, and a required result image.
4. Save the card.
5. Use Explore/Library, search, filters, and detail view to browse and copy prompts later.

## Portable backup and safe restore

Stop the app, then create a timestamped backup archive:

```bash
./scripts/backup.sh
```

Installed Windows, macOS, and Linux releases use the same engine through:

```bash
image-prompt-library backup
image-prompt-library verify-backup /safe/place/backup.tar.gz
image-prompt-library restore /safe/place/backup.tar.gz --yes
```

The backup includes:

- `library/db.sqlite`
- `library/originals/`
- `library/thumbs/`
- `library/previews/`
- `library/generation-results/`
- `library/generation-references/`

The archive uses a fixed `manifest.json` plus `library/...` layout with per-file sizes and SHA-256 checksums. Before creating it, the command applies the same credential-path boundary as application startup, refuses an auth/config path inside the library, and rejects unsafe library paths, links, or non-regular payload files. App-owned OAuth credentials, provider config, and device-login/session state stay outside the archive by construction.

This is an allowlist, not a content scrubber. Prompts, notes, generation history, and images deliberately stored in the library are included; do not put secrets in library content.

Stop the app before backup or restore. Restore validates and stages the complete archive before replacing the active path, preserves the previous library as a sibling, and rejects the former manifest-less `backup.sh` format instead of guessing how to import it.

See [`BACKUP_AND_RESTORE.md`](BACKUP_AND_RESTORE.md) for the exact payload, credential boundary, commands, failure behavior, and non-goals. Keep backups somewhere outside the repo and outside the active library if the library matters to you.

## Tests and contribution workflow

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for tests, linting, and project structure.
