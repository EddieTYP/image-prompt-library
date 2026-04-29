# Roadmap

## Public AGPL local-install MVP

Goal: make Image Prompt Library easy for someone to clone from GitHub, run on their own device, and use as an open-source local-first prompt/image manager under AGPL-3.0-or-later. Commercial licenses are available for organizations that need terms outside the AGPL.

### Must-have before public alpha

- Public-facing README with generic install instructions and no machine-specific absolute paths.
- One-command setup and start scripts.
- Clear `.env.example` configuration for library path, host, and ports.
- Friendly first-run behavior with an empty library and obvious Add CTA.
- Backup and restore guidance for runtime data.
- Smoke-test script for a running local instance.
- Tests/build passing from a fresh checkout.
- Runtime data ignored by git.
- AGPL-3.0-or-later license wording plus clear commercial license option for non-AGPL terms.
- `/media` route must not expose database, config, or internal files.

### Correctness hardening

- Prefer `result_image` for card/detail hero images.
- Treat only `result_image` as satisfying required result-image checks.
- Add DB-level validation for image roles.
- Clean up or roll back prompt-only items if required image upload fails.
- Verify optional sample-library install idempotency.

## Current v0.4 preview direction

The current 0.4 preview keeps the public site as a multilingual provenance-aware **Online Read Only Demo** while highlighting the new local-only generation workflow. Visitors can browse, search, inspect images and prompts, switch UI language, and copy public sample prompts directly from GitHub Pages. Users who want to build or edit their own private vault, or use ChatGPT OAuth direct image generation, should install and run the project locally.

Implemented focus areas:

- Public wording describes GitHub Pages as a read-only sample vault that is directly useful for browsing/copying prompts, while Add/Edit/private library management remain local-install features. The product value is the local-first library structure/workflow, not ownership of bundled sample images.
- GitHub Pages policy posture remains static and read-only: no accounts, payments, checkout, SaaS workflow, or hosted private library; clone/local-install guidance is informational.
- Demo default language is English unless the visitor has an existing saved UI-language preference.
- UI language switching updates interface chrome, collection names, and prompt-copy language labels; item titles honor the upstream/source title rather than being auto-translated.
- Prompt provenance is stored in schema v2 manifests and SQLite prompt metadata. Each item records exactly one original/source prompt language, and the original-language tab is visually marked in detail/read flows.
- Prompt tabs and copy preference use normal language variants plus an Origin/原文 logical option. English UI shows `Origin`, `English`, `zh-Hant`, `zh-Hans`; Chinese UI shows `原文`, `英文`, `繁中`, `簡中`.
- Sample packages were rebuilt from upstream sources with original prompt language, derived conversion/translation provenance, collection names, tags, source metadata, and attribution. The public static demo now combines `wuyoscar/gpt_image_2_skill` and `freestylefly/awesome-gpt-image-2`.
- Public attribution prominently thanks and links both sample-data contributors/sources, while keeping their sample-content licenses separate from the app's AGPL core.

Translation/provenance status:

- Every public sample item now carries English, Traditional Chinese, and Simplified Chinese prompt variants. Source text remains marked as source/original, OpenCC script conversions are marked as conversions, and machine-filled missing-language variants are marked as derived translations.

Mobile-native browsing remains in scope:

- Mobile opens into Cards view by default when no previous preference is saved.
- Cards use a touch-first dense two-column layout on phones, with visible copy/favorite/edit actions where those actions are available.
- Explore should eventually become a contained mobile canvas: one-finger pan, two-finger pinch zoom, and no whole-page pinch distortion while exploring.
- Mobile Explore should favor a more vertical thumbnail constellation layout instead of a wide desktop-style map.
- Detail view uses a mobile stack: image on top, close floating at the image top-right, favorite/edit floating at the image bottom-right, and prompt/metadata/tags below.
- Filters, Config, and Manage use full-height mobile drawers.
- Mobile management remains supported for local installs: add/edit, result image upload, optional reference image, multilingual prompts, tags, favorite, and archive/delete.

### Nice-to-have after public alpha

- Native Windows PowerShell scripts or a Docker Compose local install path; WSL 2 is the practical Windows route for now.
- Additional sample/demo packs or screenshots beyond the current `sample-data-v1` bundle.
- Export/import backup archive workflow in the UI.
- Full interface language setting.
- Optional semantic/vector search.

## Versioned installer / updater

Goal: make Image Prompt Library easy to install and update from tagged releases without requiring normal users to clone the repository or repeatedly run `git pull`.

Current MVP status:

- `scripts/install.sh` downloads selected GitHub Release assets, verifies SHA256, extracts under `~/.image-prompt-library/app/versions/<version>/`, and switches `app/current`.
- Normal users can install the latest release or a selected tag with `--version <tag>`.
- Installed apps expose `image-prompt-library start`, `version`, `update --version <tag>`, and `rollback` through `scripts/appctl.sh` / the install shim.
- Release artifacts are packaged by `scripts/package-release.sh` and include backend code, runtime scripts, public docs, `pyproject.toml`, and the built frontend at `frontend/dist`.
- Normal release installs do not require Node.js; Node remains part of source/development setup.
- Durable private library data stays outside the versioned app directory, defaulting to `~/ImagePromptLibrary`, while app config/auth stays under `~/.image-prompt-library/`.
- GitHub Pages remains read-only and informational. The installer path does not introduce hosted accounts, checkout, payment, SaaS sync, or public/private library hosting.

Next release work:

- Push the current installer work, tag the next alpha, let `.github/workflows/release-assets.yml` publish `tar.gz`, `.sha256`, and `.manifest.json` release assets, then verify a real GitHub Release install/update/rollback path.
- Optional polish later: release list command, interactive version chooser, status/stop helpers, Docker or native Windows scripts.

Planning doc: [`docs/plans/versioned-installer-updater.md`](docs/plans/versioned-installer-updater.md).

## Import and agent-ingestion roadmap

Goal: make it easy to pull useful prompt/image references from external repositories and public social posts into the local library through a reviewable import-draft flow. These importers should stay local-first and user-confirmed rather than becoming an automated hosted scraping service.

Status note: Batch 5 generic URL plus X/Threads import remains the next import feature batch, but it is now queued behind the versioned installer/updater work so normal users do not need to pull the full repo for every update.

Current status: **Batch 1 ImportDraft core**, **Batch 2 local markdown repository ingestion**, **Batch 3 GenerationJob plus result inbox foundation**, **Batch 4 `openai_codex_oauth_native` backend/provider UI**, **Batch 4.4–4.7 Generation UX/result workflow polish**, and the **versioned installer/updater MVP** are implemented. Generation jobs can be created provider-agnostically, receive manually staged or native Codex-provider staged result images under `generation-results/`, be listed/reviewed, and be explicitly attached to the current item or saved as a new variant item after metadata review. The Config drawer lists optional generation providers and exposes the native Codex connect/poll/disconnect controls for local installs. Generation controls are hidden until a provider is configured/authenticated, provider availability refreshes after OAuth, failed jobs get friendly failure states, and the compact queue drawer shows active/review/failed work. Next implementation milestone after publishing installer release assets: **Batch 5 generic URL plus X/Threads import**.

Shared architecture:

- Use a common `ImportDraft` pipeline for all import sources.
- Source adapters produce drafts with candidate images, prompts, source URL/repo metadata, author/handle when available, suggested collection, suggested tags, language/provenance metadata, and confidence/warnings.
- The UI should present a preview/confirm screen before writing anything into the library.
- Imported items must preserve original source text and URL/repo provenance; Traditional Chinese variants can be generated from Simplified Chinese through the existing normalization/OpenCC path and marked as derived.
- Duplicate detection should compare source URLs, image hashes when available, and normalized prompt text.

Planned adapters / agent skills:

- **Agent skill: pull dataset from repository** — scan a local markdown folder or GitHub repository for prompt-gallery style data, images, metadata, and prompt blocks; download/copy media into an import staging area; emit `ImportDraft` records for user review.
- **Agent skill: pull X/Threads posts** — given X/Twitter or Threads post/thread URLs, fetch public post text, images, quoted/replied context when accessible, author/source metadata, and generate draft tags/collection suggestions before user-confirmed import.
- **Generic URL import adapter** — given a public web URL, attempt to extract visible post/article text, image assets, Open Graph metadata, author/source metadata, and candidate prompts into `ImportDraft` records.
- **Instagram URL import adapter** — lower-priority experimental adapter because login/browser-session requirements and anti-bot behavior are likely; treat it as separate from the initial generic URL/X/Threads work.

Recommended order:

1. **Batch 1: ImportDraft core — done in backend.** Schema, staging storage, preview/list/detail/confirm API, duplicate checks, Traditional Chinese derived normalization on accepted items, and accept-draft writes into the normal library repository layer are implemented and tested.
2. **Batch 2: repository/dataset ingestion MVP — done for local markdown repositories.** The backend can scan local markdown folders, extract heading/fenced-prompt/image records, stage repository images safely under the selected library, preserve source file/ref metadata, and emit ImportDraft records for review. Future hardening can add remote GitHub clone/download orchestration and richer dataset-specific parsers.
3. **Batch 3: GenerationJob plus result inbox foundation — done in backend.** Provider-agnostic generation job records, manual/stub result staging under `generation-results/`, list/detail review API, accept/discard lifecycle, and accept-to-library media attachment are implemented and tested.
4. **Batch 4: `openai_codex_oauth_native` — backend/provider UI slices done.** The backend now has an app-owned native Codex auth store outside the library, frontend-ready optional provider status, device-code start/poll helpers, disconnect, env/local-config client-id bootstrap, access-token refresh before expiry, Codex-compatible headers with `ChatGPT-Account-ID`, a provider runner that calls the Codex Responses `image_generation` path, and `POST /api/generation-jobs/{job_id}/run` to stage generated results into the existing result inbox. The frontend Config drawer now loads provider status, shows manual/native Codex provider cards, keeps demo mode read-only/local-only, and supports native Codex connect, auth polling, and disconnect. Remaining work includes live-account QA, refresh lock hardening, Text+Reference/Image Edit payloads, retry controls, and stable native-client configuration.
5. **Batch 4.4: Generation UX/result inbox frontend first slice — done for local installs.** Local item detail views expose `Generate variant`, create GenerationJobs from saved prompts, show a result inbox, support manual result upload as an advanced/fallback path, can run provider jobs when a provider is available, and accept/discard reviewed outputs without changing the public read-only Pages demo.
6. **Batch 4.5: Generation Result UX correctness — done.** Generated results are served through the app media route before accept, item detail supports first-class multi-image browsing, manual result upload is demoted from the primary flow, provider runs show a pending shimmer card, completed results fade in, and accepting a result gives toast feedback.
7. **Batch 4.6: Save as new variant item — done.** Users explicitly choose `Attach to current item` or `Save as new item`; save-as-new creates a new variant item from a GenerationJob result, preserves source item / source generation job / provider-model provenance, and shows a metadata review/edit panel before creating the item.
8. **Batch 4.7: Generation workflow polish — done.** The app now has separate Add and Generate entries, provider-gated generation controls, mobile Generate variant, mobile metadata-panel auto-scroll/focus, a compact generation queue drawer, post-OAuth provider refresh, confirm-save navigation back to the library, and friendly policy/rate-limit/auth/provider failure states.
9. **Versioned installer/updater MVP — done.** Normal users can install/update from selected release assets without cloning or pulling source; app code is versioned under `~/.image-prompt-library/app/versions/`, private library data stays outside app code, runtime installs do not require Node.js, and update/rollback commands are available.
10. **Batch 5: generic URL plus X/Threads import** — public URL extraction and social-post/thread import behind local-only/experimental warnings.
11. **Batch 6: Instagram import** — only after the generic URL and X/Threads flow is useful, because IG auth/browser-session requirements and anti-bot behavior make it less reliable.

Keep all live-import and generation flows independent from the public GitHub Pages demo; Pages remains read-only and does not perform live imports or generation.

## Private/local generation roadmap

Goal: let local installs generate new images from saved prompts, review results, and attach accepted outputs back into the local library with explicit provenance. This remains private/local-only and should not change the GitHub Pages demo from read-only browsing/copying.

Planned provider-adapter architecture:

- Core app now owns provider-agnostic `GenerationJob` records, a generated-result inbox, review/confirm attach flow, and provenance fields in the backend.
- Initial/adaptable providers can include `manual_upload`, `openai_api_key`, external `gpt-image` CLI, Hermes-backed providers, and a native `openai_codex_oauth_native` provider.
- Edward's preferred direction is to implement `openai_codex_oauth_native` directly rather than relying only on Hermes as the broker.

`openai_codex_oauth_native` current backend slice:

- Local-only experimental adapter labelled as OpenAI via ChatGPT/Codex login, no `OPENAI_API_KEY` required.
- Uses an app-owned auth file outside the prompt library by default: `~/.image-prompt-library/auth.json`, overrideable with `IMAGE_PROMPT_LIBRARY_AUTH_PATH`; saved auth files are written with restrictive permissions where supported.
- The device-code helper can start the Codex/ChatGPT device-code flow and poll/exchange approved device auth into the app-owned token store. Starting the flow uses the same public native Codex OAuth client id as the upstream Codex CLI by default; `IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID` or local config at `~/.image-prompt-library/config.json` / `IMAGE_PROMPT_LIBRARY_CONFIG_PATH` can override it; tokens are never returned by status/API responses.
- `GET /api/generation-providers` lists `manual_upload` plus optional native Codex provider capability/status for frontend gating; the Config drawer now renders those provider cards in local installs and a demo-only read-only fallback on GitHub Pages.
- `GET /api/generation-providers/openai-codex-native/status` returns frontend-ready optional provider state (`not_configured`, `not_connected`, `connected`), configured/authenticated/available flags, feature gates, and redacted account/path metadata only.
- `POST /api/generation-providers/openai-codex-native/auth/start` starts the device-code login and returns `user_code`, `verification_url`, `device_auth_id`, `interval`, and expiry metadata.
- `POST /api/generation-providers/openai-codex-native/auth/poll` polls device authorization and saves tokens when approved.
- `POST /api/generation-providers/openai-codex-native/auth/disconnect` deletes only the app-owned token store and returns the updated redacted status.
- The auth store refreshes expired access tokens before use using the saved refresh token; cross-process refresh locking remains a follow-up.
- `scripts/codex_native_oauth_smoke.py` provides backend-only `status`, `start`, `poll`, `disconnect`, and live `generate` commands for OAuth/generation QA before building UI.
- `POST /api/generation-jobs/{job_id}/run` runs queued jobs whose provider is `openai_codex_oauth_native`, calls the Codex Responses API with the `image_generation` tool, decodes the streamed base64 PNG, and stages it into `generation-results/<job_id>/` with provenance metadata.
- Codex-compatible headers include a Codex CLI-style originator/user-agent and `ChatGPT-Account-ID` decoded from the OAuth JWT when available.
- Accepted results still flow through the Batch 3 review path: accept copies into normal `originals/`, `thumbs/`, and `previews/`; discard leaves the item untouched.

`openai_codex_oauth_native` remaining hardening:

- Add cross-process token refresh locking; failed refresh should require re-login rather than silently falling back.
- Live-account QA against the current ChatGPT/Codex backend and clearer error mapping for auth expiry, Cloudflare/challenge, empty image results, and upstream API drift.
- Add Text+Reference→Image and Image Edit request payload support using `reference_image_ids`; current backend slice covers Text→Image-style jobs.
- Add retry controls and richer job state transitions around running/failed/retry attempts.
- Continue polishing the local-only Generation UX after the current 4.7 slice: fuller retry flows, richer history/status for queued jobs, Text+Reference/Image Edit payload UI, and clearer fresh-OAuth onboarding.
- Treat this adapter as experimental because it depends on the ChatGPT/Codex backend rather than the stable public OpenAI Images API.

## Current non-goals

- Hosted SaaS accounts.
- Built-in cloud sync.
- Public prompt sharing.
- Committing user runtime data into the repository.
