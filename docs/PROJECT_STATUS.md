# Maintainer Log

Last updated: 2026-04-28

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

- title, collection, metadata, prompts, tags, and notes can be edited in place in local-install mode
- edits should use explicit confirm/cancel controls rather than blur-only auto-save
- read/detail prompt tabs should show English, Traditional Chinese, and Simplified Chinese consistently, including empty tabs for languages that are missing or only machine-derived later
- the language that is the source/original prompt should be visually distinguished in both selected and unselected tab states, instead of requiring a long tab label such as `zh-Hans (Origin)` on the tab itself
- prompt labels follow UI language: English UI uses `English`, `zh-Hant`, `zh-Hans`; Chinese UI uses `英文`, `繁中`, `簡中`; provenance badges/tooltips can still render `zh-Hans (Origin)` / `簡中（原文）` inside the prompt panel
- Origin is a first-class provenance property and should carry its detected/source language, but the editor should not expose a separate Origin prompt block
- prompt copy/edit actions apply to the active prompt tab
- Prompt Copy Language should include Origin/原文 in addition to English/英文, Traditional Chinese/繁中, and Simplified Chinese/簡中
- local-install edit mode should show exactly the normal prompt language blocks, each with an `is source/original` checkbox beside the block title; exactly one prompt can be marked original, and selecting a different one should require unchecking or otherwise explicitly moving the original marker
- empty prompt tabs remain clickable/editable in local-install mode so missing translations can be added later
- notes are separate from prompts and should stay visually lightweight when empty
- tags stay near the bottom with a clear add/remove flow

### UI language and sample-vault behavior

The public GitHub Pages site should feel like a rich read-only prompt vault rather than a throwaway demo:

- public Pages default UI language should be English unless localStorage already contains a user preference
- switching UI language should update interface chrome, collection names, sample attribution/remark text, and prompt-language labels
- item titles should honor the source/original title and should not be auto-translated just because the UI language changes
- sample attribution/remark copy should begin with a UI-language-specific attribution sentence, then preserve source/license/manifest provenance
- the `English` option inside the UI-language selector should remain spelled `English`; other Chinese-mode labels can use `英文`
- public wording should describe Pages as a static read-only vault where visitors can browse/search/view/copy public sample prompts
- public wording should make clear that the main product value is the local-first library architecture/workflow, not ownership of the bundled sample images
- README/public docs should visibly thank the sample sources/contributors (`wuyoscar/gpt_image_2_skill` and `freestylefly/awesome-gpt-image-2`) and keep sample-content licensing separate from the app code license
- Add/Edit/private management should remain clearly local-install only
- the clone/local-install path should be informational and should not turn the Pages site into a checkout, SaaS, account, or commercial transaction flow

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
- added a GitHub Actions CI workflow for Python tests, local frontend build, and demo build
- drafted `docs/releases/v0.1.0-alpha.md` as public-safe alpha release notes
- verified a fresh clone setup/start/smoke-test path on a non-reserved port with Python 3.12, including empty-library onboarding and public sample-library installation
- after public release, set the GitHub repo homepage to the read-only sandbox URL, polished README badges/release/demo affordances, drafted launch-post copy in the MacBook Downloads folder, verified unauthenticated public sample-data installation, and added SHA256 verification for the sample image ZIP
- verified tests and frontend build before the latest public-alpha preparation commit
- promoted the current preview to `v0.3.0-alpha` positioning: a multilingual provenance-aware prompt vault rather than a small patch on the 0.2 mobile preview
- added versioned `/v0.3/` Pages output while preserving `/v0.2/` and `/v0.1/` as archived previews

## Sample data notes

The public sample path is the optional sample library installer:

```bash
./scripts/install-sample-data.sh en
./scripts/install-sample-data.sh zh_hant awesome-gpt-image-2
```

Sample metadata manifests live in `sample-data/manifests/`. Larger sample image bundles are distributed separately as release assets so runtime/generated media are not committed to the repo.

Sample content must preserve third-party attribution and license metadata. The app's own code license does not automatically relicense sample content.

Sample manifests now use a formal `schema_version: 2` provenance contract:

- each item identifies exactly one existing prompt language as Origin/原文, rather than adding a separate editable Origin prompt block
- the origin/source prompt records its detected/source language (`en`, `zh_hant`, `zh_hans`, or another explicit language code when needed)
- source-provided English and Chinese prompts remain source text unless explicitly marked as derived
- Traditional/Simplified Chinese conversion is marked as derived when generated from the other Chinese script
- machine-translated prompt variants are explicitly marked as derived/translated; current sample manifests now carry English, Traditional Chinese, and Simplified Chinese prompt records for every public sample item
- README/demo copy explains that the original/source prompt is normally the best prompt to reproduce a result close to the sample image
- collection names are localized via manifest metadata, while titles preserve upstream/source wording
- the static demo bundle combines both sample packages and exports 510 compressed public sample references

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

## Mobile UX direction

The next product polish focus is a mobile-native experience rather than a scaled-down desktop layout:

- Mobile should default to **Cards** when there is no saved user view preference; Cards is the primary mobile browsing mode.
- Mobile Cards should support dense browsing with a stable two-column masonry layout on phones, with touch-visible actions for copy/favorite/edit flows.
- Mobile Explore should be a contained interactive canvas: the page itself should not pinch-zoom or distort while the Explore surface supports one-finger pan and two-finger pinch zoom.
- Mobile Explore layout should favor a vertical constellation/spine distribution instead of a wide desktop-style map.
- Mobile detail view should stack image above content. The close control floats at the top-right of the image area; favorite and edit controls float at the image bottom-right; prompt, metadata, tags, and notes sit below.
- Mobile Filters, Config, and Manage surfaces should use full-height drawers/sheets with internal scrolling and safe-area padding.
- Mobile management remains in scope: add/edit, result image upload, optional reference image, multilingual prompts, tags, favorite, and archive/delete should be usable on a phone.

Recommended implementation order:

1. Mobile shell and Cards default/columns/actions.
2. Mobile detail modal stack and copy/favorite/edit controls.
3. Full-height mobile drawers for Filters, Config, and Manage.
4. Mobile Explore gesture containment, vertical layout, and mobile thumbnail budgets.

## Known follow-ups

Public-alpha follow-ups that remain useful:

- enable private vulnerability reporting in GitHub settings if available
- consider native Windows PowerShell scripts or Docker Compose for easier cross-platform setup
- add export/import backup archive UI
- continue mobile Explore gesture/contained-canvas polish after the current Cards/detail improvements
- consider optional semantic/vector search

## Maintainer note policy

Keep this file public-safe:

- Do not include credentials, tokens, private URLs, private machine paths, or local chat/tooling notes.
- Do not include user runtime library data or screenshots that reveal private content.
- Prefer durable product decisions, verification notes, and release-preparation state.
- Put temporary local scratch notes in ignored local work files instead of this tracked document.
