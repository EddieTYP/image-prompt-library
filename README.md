# Image Prompt Library

Local-first web app for collecting, browsing, searching, categorizing, and reusing high-quality AI image prompts and generated images.

Planning source: `/Users/edwardtsoi/hermes-agent/.hermes/plans/2026-04-25_113449-local-first-image-prompt-library-webapp.md`

## What it is

Image Prompt Library is a personal desktop-browser reference tool for:

- importing the existing OpenNana / ChatGPT Image2 prompt gallery;
- keeping prompts in Traditional Chinese, Simplified Chinese, English, or original text;
- browsing prompt/image references by cluster and card grid;
- searching across titles, prompts, tags, clusters, sources, and notes;
- opening a detail view and copying prompts quickly;
- adding new local image prompt references with uploaded images.

The app is intentionally local-first. Code lives in git; runtime library data lives in a repo-local ignored `library/` directory.

## Stack

- Backend: FastAPI, SQLite, Pydantic, Pillow
- Frontend: React, Vite, TypeScript, Tailwind CSS, Radix Dialog/Tabs, Lucide icons
- Storage: `library/db.sqlite`, `library/originals/`, `library/thumbs/`, `library/previews/`
- Tests: pytest for backend/import/storage/API coverage

## Repository layout

```text
backend/                 FastAPI app, SQLite migrations, repositories, services, routers
frontend/                Vite/React app
library/                 Local runtime data (ignored except .gitkeep files)
scripts/dev.sh           Starts backend + frontend dev servers
scripts/import-opennana.sh
tests/                   Backend test suite
```

## Setup

From the repo root:

```bash
cd /Users/edwardtsoi/image-prompt-library
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
npm install
```

## Run in development

One-command dev mode:

```bash
source .venv/bin/activate
./scripts/dev.sh
```

Or run the two servers separately:

```bash
# Terminal 1: backend API on http://127.0.0.1:8787
source .venv/bin/activate
python -m uvicorn backend.main:app --reload --port 8787

# Terminal 2: frontend on http://127.0.0.1:5177
npm run dev -- --host 127.0.0.1 --port 5177
```

Open: <http://127.0.0.1:5177/>

## Import existing OpenNana gallery

The importer copies source images into the local library and creates thumbnails/previews.

```bash
source .venv/bin/activate
python -m backend.services.import_opennana \
  --source /Users/edwardtsoi/hermes-agent/.local-work/data/opennana-chatgpt-gallery/data/gallery.json \
  --library ./library
```

Convenience script:

```bash
source .venv/bin/activate
./scripts/import-opennana.sh
```

The import is duplicate-aware by slug, so rerunning it after a completed import should add `0` new items.

Current verified local import baseline:

- source `items`: 251
- source `nodes`: 271
- imported DB `items`: 251
- imported DB `images`: 542
- imported DB `clusters`: 14
- imported DB `prompts`: 745

## Verification

Backend tests:

```bash
source .venv/bin/activate
python -m pytest -q
```

Frontend build:

```bash
npm run build
```

API smoke check:

```bash
source .venv/bin/activate
python -m uvicorn backend.main:app --port 8787
curl http://127.0.0.1:8787/api/health
curl 'http://127.0.0.1:8787/api/items?limit=3'
```

Browser smoke flow:

1. Open <http://127.0.0.1:5177/>.
2. Confirm default Explore view loads.
3. Click a cluster card and confirm Cards view opens.
4. Search for a title/prompt/tag and confirm visible results update.
5. Open a card detail modal and copy a prompt.
6. Open Add, create an item with an image, and confirm it appears.
7. Open Config and confirm the placeholder/library path renders.
8. Confirm browser console has no errors.

## Data and backup notes

`library/` is intentionally ignored by git. Before relying on the app as the only copy of important prompts/images, back up at least:

```text
library/db.sqlite
library/originals/
library/thumbs/
library/previews/
```

A later export/backup command should package these into a timestamped archive or sync target.

## MVP status

Implemented vertical slice:

- SQLite schema and migrations
- item repository and FTS search rebuild
- image storage with thumbnails/previews
- FastAPI item/image/cluster/tag/import routes
- OpenNana importer
- React top chrome, filters panel, Explore view, Cards view, detail modal, add/edit modal, config placeholder
- real OpenNana import into local `library/`

Deferred by design:

- cloud sync / accounts / public sharing
- semantic/vector search
- advanced Orbit/graph UI
- full mobile polish
- robust backup/export workflow
