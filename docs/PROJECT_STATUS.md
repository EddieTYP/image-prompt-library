# Maintainer Log

Last updated: 2026-04-29

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

### Generation result workflow

GenerationJob is a temporary workbench/result inbox, not an automatic commit into the library. Generation results should not be silently attached to the source item. After a provider run completes, the user explicitly chooses the result disposition.

Final accepted direction for the next generation-UX batches:

- Result inbox cards expose an explicit accept action and discard action.
- Accept should become a split/dropdown action with two choices:
  - `Attach to current item`
  - `Save as new item`
- `Attach to current item` appends the generated image to the current item, keeps generation metadata, and shows a toast: `Image added to item`.
- `Save as new item` creates a new variant item whose primary image is the generated result, uses the generation prompt, preserves provenance back to the source item and GenerationJob, and shows a toast: `New variant item created` with a `View item` action.
- If an item has multiple images, the detail modal must support first-class image browsing: main image area, thumbnail/dot switcher, visible position such as `1 / 2`, and click-to-switch behavior.
- Generated/variant images should carry visible role/provenance badges where practical.
- Provider runs should show an animated shimmer/skeleton image placeholder in the result inbox rather than a plain spinner.
- When a result completes, the pending card should transition into the result card with a subtle fade-in.
- After accept, use toast feedback rather than an interrupting modal; when attaching, select/highlight the newly attached image in the item detail if possible.
- Manual result upload should be hidden or demoted from the primary generation flow. Its real purpose is uploading an externally generated result into a GenerationJob, not normal item creation; keep backend support available but do not present it beside the main provider run/accept controls unless exposed as an advanced/fallback action.

Current user-reported bugs to fix before adding more generation features:

- Accepted generated images can render as broken image placeholders instead of loading through the app media route.
- Items with more than one image cannot currently browse/switch to the second image from the detail UI.

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

Next implementation focus:

0. **Versioned installer / updater — MVP implemented, release publication next**: normal users can install/update a tagged release without cloning the repo or running `git pull`. The installer downloads GitHub Release artifacts, verifies SHA256, extracts versioned app directories under `~/.image-prompt-library/app/versions/`, switches `app/current`, preserves durable user data outside app code, and supports selected versions plus rollback. Release artifacts include the built frontend at `frontend/dist`, so normal release installs do not require Node.js. Remaining work is to push/tag the next public release and verify real GitHub Release download end-to-end.
1. **ImportDraft core — done in backend**: persistent schema/storage, preview/list/detail/confirm API, duplicate checks, derived Traditional Chinese normalization on accepted items, and accept-draft writes into the normal library repository layer are implemented and tested.
2. **Repository/dataset ingestion MVP — done for local markdown repositories**: the backend scans local markdown folders, extracts heading/fenced-prompt/image records, stages local image assets safely under the selected library, preserves source file/ref metadata, and emits ImportDraft records for review. Remote GitHub clone/download orchestration and richer dataset-specific parsers remain future hardening.
3. **GenerationJob plus result inbox foundation — done in backend**: provider-agnostic generation job records, manual/stub result staging under `generation-results/`, list/detail review API, accept/discard lifecycle, accept-to-current-item media attachment, and save-as-new-variant behavior are implemented and tested.
4. **`openai_codex_oauth_native` provider — backend/provider UI slices done**: app-owned native Codex auth store outside the library, frontend-ready optional provider status/list API, device-code start/poll/disconnect helpers, env/local-config client-id bootstrap, token refresh before expiry, Codex-compatible headers, `POST /api/generation-jobs/{job_id}/run` can stage Codex image results into the GenerationJob inbox, and the frontend Config drawer lists providers plus native Codex connect/poll/disconnect controls. Fresh OAuth onboarding QA, refresh lock hardening, reference/edit modes, model configuration UI, and retry controls remain follow-ups.
5. **Generation UX/result inbox frontend — local slice implemented**: item detail views can launch `Generate variant` only when a provider is connected, standalone Generate is available in local installs with a connected provider, GenerationJobs can be reviewed in a result inbox, generated results can attach to the current item or save as a new variant item after metadata review/edit, multi-image detail browsing works, manual result upload is demoted as an advanced/fallback action, and public GitHub Pages remains read-only.
6. **Generation workflow polish — implemented for current local slice**: provider availability refreshes after OAuth without manual browser refresh, confirm-save closes the generation page and returns to the library, mobile Generate variant is provider-gated, mobile save-as-new auto-scrolls/focuses the metadata edit panel, a compact generation queue drawer shows active/succeeded/failed jobs, and policy/rate-limit/auth/provider failures use friendly states.
7. **Generic URL plus X/Threads import** — public URL extraction and social-post/thread import behind local-only/experimental warnings.
8. **Instagram import** — later experimental adapter only after generic URL and X/Threads are useful.

Public-alpha follow-ups that remain useful:

- enable private vulnerability reporting in GitHub settings if available
- consider native Windows PowerShell scripts or Docker Compose for easier cross-platform setup
- add export/import backup archive UI
- continue mobile Explore gesture/contained-canvas polish after the current Cards/detail improvements
- consider optional semantic/vector search

Private/local generation follow-ups:

- Batch 3 provider-adapter generation foundation is now implemented in the backend: `POST /api/generation-jobs` creates provider-agnostic jobs, `POST /api/generation-jobs/{job_id}/result` stages manual/stub result images under `generation-results/`, `GET /api/generation-jobs` and `GET /api/generation-jobs/{job_id}` support review/inbox reads, and accept/discard endpoints finalize the result. Accepted images are copied through normal media storage into `originals/`, `thumbs/`, and `previews/` before attaching to the source item.
- Batch 4 `openai_codex_oauth_native` backend/provider UI slices are now implemented: `backend/services/openai_codex_native.py` owns the app-native auth store (`~/.image-prompt-library/auth.json` by default, overrideable via `IMAGE_PROMPT_LIBRARY_AUTH_PATH`), frontend-ready provider status (`not_configured` / `not_connected` / `connected`), env/local-config client-id resolution (`IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID` or `~/.image-prompt-library/config.json` / `IMAGE_PROMPT_LIBRARY_CONFIG_PATH`), redacted token status, device-code start/poll helpers, disconnect, access-token refresh before expiry, `ChatGPT-Account-ID` JWT header extraction, Codex-compatible headers, Codex Responses `image_generation` streaming, and result staging through the existing GenerationJob inbox. `backend/routers/generation_providers.py` exposes list/status/auth endpoints, `backend/routers/generation_jobs.py` exposes `POST /api/generation-jobs/{job_id}/run`, `scripts/codex_native_oauth_smoke.py` provides backend-only live OAuth/generation smoke commands, and `frontend/src/components/ConfigPanel.tsx` now lists manual/native Codex provider cards with connect, poll, and disconnect controls while keeping GitHub Pages demo mode read-only/local-only. Fresh OAuth onboarding QA, cross-process refresh lock hardening, Text+Reference/Image Edit payloads, model configuration UI, and retry controls remain follow-ups.
- Batch 4.4 through 4.7 generation UX is implemented for the current local slice: local item detail views expose provider-gated `Generate variant`, standalone Generate appears only when a provider is connected, GenerationJobs are reviewed through a result inbox, manual external upload is demoted, generated images load through the app media route, item detail supports multiple images with thumbnail/counter browsing, users choose `Attach to current item` or `Save as new item`, save-as-new opens an editable metadata review panel before creating a variant item, confirm-save returns to the library, provider availability refreshes after OAuth without a manual browser refresh, mobile save-as-new scrolls/focuses the metadata editor, a compact generation queue drawer shows work status, and friendly failure states cover policy/rate-limit/auth/provider errors.
- keep `openai_codex_oauth_native` local-only and experimental; it uses the ChatGPT/Codex backend, not the stable public OpenAI Images API
- device-code login should create this app's own OAuth session and token store, separate from other local auth stores by default
- token storage must live outside the library/export/demo data path, use restrictive permissions, refresh before expiry, and never enter git, sample bundles, backups, or GitHub Pages exports; cross-process refresh locking remains follow-up hardening
- request handling must decode the OAuth JWT for `ChatGPT-Account-ID`, send Codex-compatible originator/user-agent headers, call the Codex Responses API with the `image_generation` tool and `gpt-image-2`, parse streamed base64 image output, and save results into a local review inbox
- generated-output provenance should record provider `openai_codex_oauth_native`, auth mode `codex_oauth_native`, model/provider details, quality/size/aspect ratio, prompt variant, reference images, source item id, generation job id, timestamps, and user disposition

Import and agent-ingestion follow-ups:

- Batch 1 ImportDraft core is now implemented in the backend: source adapters can create persistent draft records with prompts/media/provenance metadata, reviewers can list/preview drafts, duplicate drafts are detected by source URL or normalized prompt text, and accepted drafts create normal library items through the existing repository layer.
- Batch 2 repository/dataset ingestion MVP is implemented for local markdown repositories: `POST /api/import-drafts/repository` scans a local folder, extracts Markdown heading/fenced-prompt/image records, stages image assets under `import-staging/`, stores image dimensions/SHA256 when available, preserves repo URL/ref/source path metadata, and emits ImportDraft records for review before accept.
- future repository-ingestion hardening should add remote GitHub clone/download orchestration, richer dataset-specific parser adapters, license/attribution extraction, and optional tag suggestions
- add an agent skill / adapter to pull X/Twitter and Threads post or thread URLs into `ImportDraft` records with public post text, media, source URL, author/handle, quoted/replied context when accessible, and suggested collection/tags
- add a generic public URL import adapter for article/post pages that can extract visible text, images, Open Graph metadata, author/source metadata, candidate prompts, and suggested collection/tags into reviewable drafts
- track Instagram URL import as a later experimental adapter rather than the first URL-import target, because login/browser-session requirements and anti-bot behavior are likely
- implement repository/dataset ingestion before URL/social import because repos are more stable and testable; then do generic URL plus X/Threads; only consider Instagram after those are useful
- both import flows must preserve source/original text, generate Traditional Chinese only as a marked derived variant when applicable, deduplicate by source URL/image hash/normalized prompt text, and never run inside the public read-only Pages demo

## Maintainer note policy

Keep this file public-safe:

- Do not include credentials, tokens, private URLs, private machine paths, or local chat/tooling notes.
- Do not include user runtime library data or screenshots that reveal private content.
- Prefer durable product decisions, verification notes, and release-preparation state.
- Put temporary local scratch notes in ignored local work files instead of this tracked document.
