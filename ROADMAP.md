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

## Current non-goals

- Hosted SaaS accounts.
- Built-in cloud sync.
- Public prompt sharing.
- Committing user runtime data into the repository.
