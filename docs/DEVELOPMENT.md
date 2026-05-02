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
```

Do not commit runtime `library/` data to git. It is your private prompt/image collection.

## Add your own prompts and images

1. Start the app.
2. Click `+ Add`.
3. Add a title, prompt text, collection, optional tags, and a required result image.
4. Save the card.
5. Use Cards/Explore, search, filters, and detail view to browse and copy prompts later.

## Backup

Create a timestamped backup archive:

```bash
./scripts/backup.sh
```

The backup includes:

- `library/db.sqlite`
- `library/originals/`
- `library/thumbs/`
- `library/previews/`

Restore by stopping the app, extracting the archive, and replacing the corresponding library directory contents. Keep backups somewhere outside the repo if the library matters to you.

## Tests and contribution workflow

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for tests, linting, and project structure.
