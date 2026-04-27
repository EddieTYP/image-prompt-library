# Maintainer Log

Last updated: 2026-04-27

This file records public-safe maintainer notes for the Image Prompt Library project. It is intentionally more detailed than `ROADMAP.md`, but it should not contain private machine paths, credentials, runtime data, or local workflow details.

For the public product roadmap, see [`../ROADMAP.md`](../ROADMAP.md).

## Product direction

Image Prompt Library is a local-first web app for saving generated images together with their prompts, collections, tags, and source metadata.

The public alpha target is a clone-and-run local install:

- FastAPI backend
- SQLite metadata store
- local media directory for images and thumbnails
- React/Vite frontend
- AGPL-3.0-or-later application code, with commercial licensing available for organizations that need terms outside the AGPL

## Public alpha status

Current public-alpha preparation is focused on:

- clear public README and roadmap
- reproducible local setup/start scripts
- configurable local library path and app ports
- safe media serving that does not expose database/config/internal files
- ignored runtime data and generated media
- optional sample library installer with separate sample image assets
- public sample attribution for third-party demo content
- tests/build passing from a fresh checkout

The repository is intended to stay safe for public release by keeping user runtime data, private imports, local working directories, backups, and generated application state out of git.

## Core UX decisions

### Browsing modes

The app has two primary browsing modes:

1. **Explore** — a thumbnail constellation view.
   - Collection cards act as hub nodes.
   - Image thumbnails are connected item nodes.
   - The view should remain visual; it should not degrade into abstract dot-only nodes.
   - Focus mode centers one selected collection and arranges its thumbnails in a stable, readable layout.

2. **Cards** — a masonry gallery view.
   - Designed for template-marketplace-style browsing density.
   - Preserves quick actions such as copy prompt, favorite, and edit.
   - Should remain stable while images load and while users scroll.

### Main layout

Current accepted layout decisions:

- No hero section; the search bar and gallery are the entry point.
- Keep the top toolbar with search, logo/brand area, filters entry, config entry, active filter/status strip, Explore/Cards toggle, and floating Add button.
- No command-palette search shortcut for now.
- Cards mode masonry is accepted and should not be replaced with a plain grid without a deliberate design decision.
- Explore focus view is accepted; future work should be minor tuning unless the direction changes.

### Detail and editing workflow

The detail modal should be the primary lightweight editing surface:

- title, collection, metadata, prompts, tags, and notes can be edited in place
- edits should use explicit confirm/cancel controls rather than blur-only auto-save
- prompt panel uses ordered language tabs: English, Traditional Chinese, Simplified Chinese
- prompt copy/edit actions apply to the active prompt tab
- empty prompt tabs remain clickable/editable so missing translations can be added later
- notes are separate from prompts and should stay visually lightweight when empty
- tags stay near the bottom with a clear add/remove flow

## Data and security rules

Runtime data and generated media must not be committed:

- `library/db.sqlite`
- `library/db.sqlite-*`
- `library/originals/`
- `library/thumbs/`
- `library/previews/`
- `.env`
- `backups/`
- `.local-work/`

Media serving rules:

- `/media` should only expose intended media files.
- Database, config, backups, and arbitrary local paths must not be reachable through `/media`.
- `GET /media/db.sqlite` should return 404.

Port convention:

- backend default: `127.0.0.1:8000`
- frontend dev default: `127.0.0.1:5177`
- avoid using `8787` for this app because that port may be reserved by other local tools

## Implemented public-release preparation

Recent preparation work includes:

- added public repo hygiene files: `SECURITY.md` and GitHub issue templates
- switched README project-status link to `ROADMAP.md`
- published sample-data release asset `sample-data-v1`
- updated public sample documentation around the release asset and private-repo visibility caveat
- removed source-specific gallery import workflows from the public app surface
- added tests guarding that removed importer surfaces stay absent
- added tests guarding public docs, install helpers, runtime ignore rules, and media lockdown
- pinned frontend dependency versions instead of using `latest`
- added tests preventing npm dependency specs from regressing to `latest`
- added a GitHub Pages read-only online sandbox build using static JSON and compressed public sample images
- added demo-mode guards that keep browsing/search/copy available while disabling Add/Edit/Favorite/tag/prompt mutations
- added a compact demo-data export script for the public sample library and regression tests for the Pages workflow, demo disclosure, and generated static bundle
- verified tests and frontend build before the latest public-alpha preparation commit

## Sample data notes

The public sample path is the optional sample library installer:

```bash
./scripts/install-sample-data.sh en
```

Sample metadata manifests live in `sample-data/manifests/`. The larger sample image bundle is distributed separately as a release asset so runtime/generated media are not committed to the repo.

Sample content must preserve third-party attribution and license metadata. The app's own code license does not automatically relicense sample content.

## Verification checklist

Before switching the repository public or tagging an alpha release, verify:

- `python -m pytest -q`
- `npm run build`
- `git diff --check`
- no tracked runtime database/media/backups/local-work artifacts
- no credentials or secret-looking values in the current tree
- no private machine paths in public docs
- fresh clone setup succeeds with Python 3.10+
- app starts on non-reserved ports
- `/api/health` returns OK
- unknown `/api/*` routes return 404
- `/media/db.sqlite` returns 404
- empty-library first-run UI has a clear Add action
- sample installer works after public release assets are reachable without authentication

## Known follow-ups

Public-alpha follow-ups that remain useful:

- retest unauthenticated sample installation immediately after the repository becomes public
- add checksum verification or prominently document the sample image bundle checksum
- add minimal GitHub Actions for tests and frontend build
- enable private vulnerability reporting in GitHub settings if available
- consider native Windows PowerShell scripts or Docker Compose for easier cross-platform setup
- add export/import backup archive UI
- improve mobile polish
- consider optional semantic/vector search

## Maintainer note policy

Keep this file public-safe:

- Do not include credentials, tokens, private URLs, private machine paths, or local chat/tooling notes.
- Do not include user runtime library data or screenshots that reveal private content.
- Prefer durable product decisions, verification notes, and release-preparation state.
- Put temporary local scratch notes in ignored local work files instead of this tracked document.
