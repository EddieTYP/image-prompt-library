# Image Prompt Library

A local-first web app for collecting, browsing, searching, categorizing, and reusing AI image prompts together with their generated/reference images.

The app is designed for people who want a private prompt/image reference library on their own device: no accounts, no cloud sync, and no hosted database required.

## Features

- Local SQLite database and local image files.
- Image storage with originals, previews, and thumbnails.
- Explore mode: thumbnail constellation view for visual browsing.
- Cards mode: masonry/Pinterest-style prompt gallery.
- Search across titles, prompts, tags, collections, sources, and notes.
- Collections and tags for organizing references.
- Detail modal with prompt language tabs and copy feedback.
- Add/edit modal with Traditional Chinese, Simplified Chinese, and English prompt fields.
- Result image and optional reference image uploads.
- OpenNana/ChatGPT prompt-gallery import path for bootstrapping a library.

## Requirements

- Python 3.10+
- Node.js 20+ recommended
- npm

## Quick start

```bash
git clone https://github.com/<your-user>/image-prompt-library.git
cd image-prompt-library
./scripts/setup.sh
./scripts/start.sh
```

Open <http://127.0.0.1:8000/>.

`scripts/start.sh` builds the frontend and serves the built app through FastAPI, so normal local use only needs one server.

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

## Add your own prompts

1. Start the app.
2. Click `+ Add`.
3. Add a title, prompt text, collection, optional tags, and a required result image.
4. Save the card.
5. Use Cards/Explore, search, filters, and detail view to browse and copy prompts later.

## Import an OpenNana gallery export

If you have an OpenNana gallery JSON export, import it with:

```bash
source .venv/bin/activate
python -m backend.services.import_opennana \
  --source /path/to/gallery.json \
  --library "${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
```

Convenience script for the default expected local export location:

```bash
./scripts/import-opennana.sh
```

The importer is duplicate-aware by slug, so rerunning a completed import should not create duplicate items.

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

## Verification

Run backend/API/static tests:

```bash
source .venv/bin/activate
python -m pytest -q
```

Build the frontend:

```bash
npm run build
```

Smoke-test a running local server:

```bash
./scripts/smoke-test.sh
```

## Privacy and security model

- The app is local-first and stores data on your device.
- There are no user accounts or built-in cloud sync.
- The `/media` route only serves image media directories and should not expose the SQLite database or internal files.
- Binding to `127.0.0.1` keeps the app local to your machine. Only change the host if you understand the LAN exposure implications.

## Troubleshooting

### `./scripts/start.sh` cannot find Python dependencies

Run setup first:

```bash
./scripts/setup.sh
```

### Port already in use

Change `.env`:

```bash
BACKEND_PORT=8001
FRONTEND_PORT=5178
```

Then restart the app.

### Empty library after first start

That is expected for a fresh install. Click `+ Add` to create your first prompt card, or import an OpenNana export JSON.

### Images or database missing after moving folders

Check `IMAGE_PROMPT_LIBRARY_PATH` in `.env`. Your database and image folders must stay together.

## Project status

This is an early local-first MVP / alpha. Core browse/search/add/edit/copy/import flows exist, but public packaging, backup/restore polish, and installation docs are still improving.

See `docs/PROJECT_STATUS.md` for the current roadmap.

## Repository layout

```text
backend/                 FastAPI app, SQLite migrations, repositories, services, routers
frontend/                Vite/React app
library/                 Local runtime data, ignored except .gitkeep placeholders
scripts/dev.sh           Backend + Vite development mode
scripts/setup.sh         Local setup helper
scripts/start.sh         Single-service local mode
scripts/backup.sh        Timestamped local data backup
scripts/smoke-test.sh    Basic running-server smoke test
tests/                   Backend/API/static regression tests
```
