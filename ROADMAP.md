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

## Current 0.3 preview direction

The current 0.3 preview positions the public site as a multilingual provenance-aware read-only prompt vault, not merely a lightweight demo. Visitors can browse, search, inspect images and prompts, switch UI language, and copy public sample prompts directly from GitHub Pages. Users who want to build or edit their own private vault should clone and run the project locally.

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

## Import and agent-ingestion roadmap

Goal: make it easy to pull useful prompt/image references from external repositories and public social posts into the local library through a reviewable import-draft flow. These importers should stay local-first and user-confirmed rather than becoming an automated hosted scraping service.

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

1. Implement the repository/dataset ingestion skill first because markdown/GitHub repos are more stable, easier to test, and map cleanly to the existing sample-manifest/provenance model.
2. Implement generic URL import and X/Threads ingestion next, behind clear local-only/experimental warnings where needed.
3. Consider Instagram only after the generic/X/Threads flow is useful, because IG auth/browser-session requirements and anti-bot behavior make it less reliable.
4. Keep all live-import flows independent from the public GitHub Pages demo; Pages remains read-only and does not perform live imports.

## Private/local generation roadmap

Goal: let local installs generate new images from saved prompts, review results, and attach accepted outputs back into the local library with explicit provenance. This remains private/local-only and should not change the GitHub Pages demo from read-only browsing/copying.

Planned provider-adapter architecture:

- Core app owns provider-agnostic `GenerationJob` records, a generated-result inbox, review/confirm attach flow, and provenance fields.
- Initial/adaptable providers can include `manual_upload`, `openai_api_key`, external `gpt-image` CLI, Hermes-backed providers, and a native `openai_codex_oauth_native` provider.
- Edward's preferred direction is to implement `openai_codex_oauth_native` directly rather than relying only on Hermes as the broker.

`openai_codex_oauth_native` target design:

- Local-only experimental adapter labelled as OpenAI via ChatGPT/Codex login, no `OPENAI_API_KEY` required.
- Use the Codex/ChatGPT device-code OAuth flow to obtain an app-owned access token and refresh token.
- Store tokens outside the prompt library data directory, for example under a user config/auth directory, with restrictive file permissions and no export into sample bundles, backups, GitHub Pages data, or the repository.
- Maintain an independent OAuth session for this app instead of mutating Hermes or Codex CLI auth stores by default, to avoid refresh-token rotation conflicts.
- Refresh tokens with locking/skew handling before expiry; failed refresh should require re-login rather than silently falling back.
- Decode `ChatGPT-Account-ID` from the OAuth JWT claim and send Codex-compatible headers such as the Codex CLI-style originator/user-agent when calling the Codex backend.
- Call the Codex Responses API at the ChatGPT/Codex backend with the `image_generation` tool, forcing `gpt-image-2` with selectable quality tiers and supported sizes/aspect ratios.
- Extract base64 PNG results from streamed `image_generation_call` output, save them into a local generation-results area, and copy accepted images into normal library media storage.
- Record provenance for generated outputs: provider `openai_codex_oauth_native`, auth mode `codex_oauth_native`, image model, host/chat model if applicable, quality, size/aspect ratio, prompt variant used, reference images if any, source item id, job id, timestamps, and whether the user accepted/retried/discarded the result.
- Treat this adapter as experimental because it depends on the ChatGPT/Codex backend rather than the stable public OpenAI Images API.

## Current non-goals

- Hosted SaaS accounts.
- Built-in cloud sync.
- Public prompt sharing.
- Committing user runtime data into the repository.
