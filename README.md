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
- Detail modal with lightweight inline editing, prompt language tabs, and copy feedback.
- Add/edit modal with English, Traditional Chinese, and Simplified Chinese prompt fields plus metadata.
- Result image and optional reference image uploads.
- Optional import adapters for bootstrapping a library from supported local/exported sources.

## Requirements

- Python 3.10+
- Node.js 20+ recommended
- npm

## Platform support

- macOS and Linux are the primary supported local-install targets today.
- Windows can run the app stack through **WSL 2** using the same commands as Linux.
- Native Windows PowerShell/CMD is not a supported quick-start path yet because the current helper scripts are Bash scripts and assume Unix-style virtualenv paths such as `.venv/bin/activate`. Native Windows support should use equivalent PowerShell scripts or a Docker/Compose path in a future pass.

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

## Import and example data

This app intentionally does not ship third-party prompt-gallery data or generated images. Runtime library data is private/user-owned and should stay outside git.

### Sample screenshot/demo dataset

For public screenshots and demo GIFs, prefer a clearly licensed sample source instead of Edward's private library or an OpenNana scrape. The current demo-data source is [`wuyoscar/gpt_image_2_skill`](https://github.com/wuyoscar/gpt_image_2_skill), whose repository `LICENSE` states **Attribution 4.0 International (CC BY 4.0)** and preserves individual prompt attributions. The planned optional sample bundle should contain the full 162-reference gallery, organized into roughly 10 Image Prompt Library collections with English, Simplified Chinese, and Traditional Chinese collection metadata.

If you load this source into a local demo library:

- keep the installed sample library out of git unless it is part of the curated sample bundle release process;
- preserve attribution/source metadata on imported or bundled records where possible;
- mention `wuyoscar/gpt_image_2_skill` and **CC BY 4.0** near any public screenshots, demo GIFs, or demo fixtures;
- review the source repository's latest license before publishing screenshots or sample data, because third-party licensing can change.

This source is a good fit for a screenshot/demo pass, and it is distributed as an explicit optional sample bundle rather than as live scraping/import instructions. Packaging is: keep curated metadata in git, publish the image bundle as a GitHub Release asset, and use `scripts/install-sample-data.sh zh_hant` / `zh_hans` / `en` to download or copy the selected bundle into the user's configured local library. If images are committed directly to the repository later, document sparse checkout / partial clone instructions so users can avoid the sample asset directory when they only want the app.

Install shape:

```bash
./scripts/install-sample-data.sh en
```

Until a release asset is published, local QA can point the installer at a local image ZIP:

```bash
IMAGE_PROMPT_LIBRARY_PATH=.local-work/sample-demo \
SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-sample-images-v1.zip \
./scripts/install-sample-data.sh en
```

Open <http://127.0.0.1:8000/> after installing a sample bundle. The curated bundle should use the original English prompts from `wuyoscar/gpt_image_2_skill`; only include Simplified/Traditional Chinese prompt fields when the source has Chinese text or an explicit translation has been reviewed. Do not force an English prompt into a Chinese prompt field. Collection names can be localized across English, Simplified Chinese, and Traditional Chinese while keeping source/license attribution metadata from the original project.

### Import an OpenNana gallery export

OpenNana support is an optional adapter for a local OpenNana gallery JSON export. It is not a universal webpage scraper and it does not download directly from arbitrary gallery pages.

Import with:

```bash
source .venv/bin/activate
python -m backend.services.import_opennana \
  --source /path/to/gallery.json \
  --library "${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
```

Convenience script:

```bash
./scripts/import-opennana.sh /path/to/gallery.json "${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
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

## License and allowed use

Image Prompt Library's core application code is open source under **AGPL-3.0-or-later**. Copyright (C) 2026 Edward Tsoi. See `NOTICE` for the project copyright notice and `LICENSE` for the full AGPL text.

Commercial licenses are available for organizations that want to use, modify, or host Image Prompt Library under terms outside the AGPL. Contact the maintainer if you need proprietary hosted-product terms or other non-AGPL licensing.

Sample data and third-party assets are licensed separately and retain their original attribution/license terms. The optional sample bundle currently preserves `wuyoscar/gpt_image_2_skill` / **CC BY 4.0** attribution; do not treat sample prompts/images as part of the app-code AGPL grant.

Your own local prompt library data remains yours and should not be committed to this repository.

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

That is expected for a fresh install. Click `+ Add` to create your first prompt card, or import a supported local/exported source through an adapter such as the OpenNana JSON importer.

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
