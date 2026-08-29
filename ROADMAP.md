# Roadmap

## Current stable direction

Image Prompt Library is a local-first prompt and image manager. The current stable release is `v0.10.2`; its public GitHub Pages demo is a static, read-only catalogue of attributed prompt/image references. Private-library management, local data, and optional ChatGPT / Codex OAuth generation remain local-install features. The application code is AGPL-3.0-or-later, with commercial licensing available for organizations that need different terms.

The project does not provide hosted accounts, checkout, payments, SaaS sync, or a hosted private library. SQLite data, images, prompts, and provider state stay on the user's machine.

## Roadmap lanes

The roadmap uses four product lanes. They are ongoing areas, not four sequential releases. Each lane records what is already shipped; all near-term planned work is consolidated in the prioritized list below.

### A. Install and onboarding hardening — current milestone complete

Native Windows Quick Start shipped in `v0.8.0`, including versioned installs, background lifecycle commands, diagnostics, transactional updates, release assets, and rollback.

Published download/install verification, Windows handled-failure recovery, source and release update UI, and macOS launchd lifecycle support are complete. POSIX update/rollback resilience, handled-interruption recovery, release gates, and exact `v0.8.0` rollback compatibility shipped through `v0.8.2`. Further installer work should respond to observed failures rather than reopen this milestone broadly.

### B. Library power-user polish — current milestone complete

The completed milestone added clearer search, sort, and filter state; backend-backed batch management; preview-first cleanup; and stronger metadata/provenance handling. Batch `Tag` and `Move` now use searchable in-app controls instead of browser prompts, including multi-select tag suggestions and an existing-Collection picker. Library create/edit and generated-result save flows also provide an explicit, opt-in `Suggest title` action that previews the suggestion before applying it.

One Library item can now hold a complete image set. Edit lets users choose the primary image, reorder images, change result/reference roles, and remove individual images. Generation batch review can add later results to the item created from the first result, while each image keeps its own provider and model details.

Any future library work should be driven by observed usability problems rather than reopening this milestone broadly.

### C. Generation workflow hardening — current milestone complete on `main`

The generation foundation, OAuth connection flow, queued jobs, result review, attach/save-as-new actions, retry controls, and session-reliability hardening are shipped.

The focused Generation Input & Reference Polish milestone is complete. Generation now supports ordered uploaded, saved-library, and prior-result references with preserved provenance across retry, review, attach, and save-as-new flows on desktop and mobile.

Manual retry, stalled-job recovery, provider-failure classification and guidance, backend-restart recovery, and the credential-path boundary are complete. OAuth credentials and session configuration are app-owned outside the library by default, and current backup, sample, and demo paths omit them.

`v0.9.0` added atomic Generation sets of 1, 3, 5, or 10 jobs, exact queue progress, a production concurrency cap of five, provider pause/backoff handling, individual review/retry semantics, and portable credential-free backup and safe restore. `v0.10.0` completed the Explore/Library redesign, Appearance presets, and continuous Generation-set review. `v0.10.1` hardened update checks against GitHub's shared anonymous request limit. `v0.10.2` refreshed the built-in GPT-5.6 orchestrator choices, made `gpt-5.6-terra` the recommended default, and retained explicit `gpt-5.6-sol`, `gpt-5.6-luna`, and custom configured choices.

The capability check through the app's ChatGPT / Codex OAuth path found that `gpt-image-2` rejects transparent backgrounds there. `v0.10.2` therefore keeps PNG output opaque and does not expose a transparent-output control. Revisit this only if the provider capability changes.

### D. External inspiration import — deferred

Local markdown repository ingestion and the shared `ImportDraft` review flow remain available. Generic URL plus X/Threads import, along with Instagram adapters, remains deferred because reliable social-post reply extraction requires platform authentication, paid APIs, or brittle scraping that does not yet meet the product's acceptance bar.

If this lane resumes, adapters must still feed candidate prompts, media, provenance, warnings, and duplicate checks into `ImportDraft` for explicit user confirmation before library writes.

## Prioritized outstanding work

1. **xAI / Grok Imagine provider feasibility** — scope `grok-imagine-image-2.0` as a separate API-key and usage-billed provider. Verify credential storage, backup/demo exclusion, generation and edit parity, reference limits, returned-media handling, errors, rate limits, privacy, and cost display before deciding whether to implement it. Do not reuse or weaken the ChatGPT / Codex OAuth boundary.

`v0.10.0` implemented Explore clarity: a normal-scroll directory of non-empty Collections, natural-ratio previews that open item detail directly, Collection heading/count routing into filtered `Library`, and the visible `Cards` rename to `Library`. Explore item detail keeps Copy, Download, Generate, and Edit while selection and batch management remain in Library. It also includes three browser-local light Appearance presets displayed as `Red`, `Green`, and `Purple` (`朱紅`、`松綠`、`茄紫`); their existing internal identifiers remain unchanged. Dark mode, system-theme following, and an arbitrary colour picker remain out of scope.

The former responsive vertical-constellation follow-up is superseded by Explore clarity and should not be implemented as a second browsing model.

## Planned update sequence

These are product and release groups, not promised version numbers. Small independent fixes may ship between them when they do not broaden the main milestone.

1. **`v0.11.0` Library workflow group** — combine the completed batch-action polish, opt-in title suggestion, reliable generated-image provider/model display, and multi-image Library workflow. Never spend provider quota without an explicit user action.
2. **Provider decision** — complete the xAI / Grok feasibility and privacy review separately. A new provider should not block `v1.0.0` unless explicitly promoted.
3. **`v1.0.0` readiness** — run final Windows and POSIX install/update/rollback/restore checks, desktop/mobile and static-demo QA, migration and privacy checks, and documentation alignment. Do not use the `v1.0.0` release gate to introduce import architecture, an account system, or other unrelated work.

## Later or optional work

- Additional curated sample/demo packs when source quality and licensing justify them.
- Complete localization coverage for the existing Traditional Chinese, Simplified Chinese, and English interface setting; the language selector itself is already shipped.
- Optional semantic/vector search after normal search proves insufficient.
- Optional local accounts with password-capable admin/editor/read-only roles and shared/private visibility.

Account work must preserve the local-first model: backend permissions protect app workflows, OS filesystem permissions protect the raw vault, existing items remain shared during migration, and GitHub Pages stays account-free and read-only.

## Product constraints

- Public GitHub Pages remains a multilingual, provenance-aware, read-only demo.
- Add, edit, generation, private-library management, and provider authentication remain local-install features.
- OAuth credentials and local session configuration stay outside libraries, backups, samples, and demo exports. Non-secret provider/model provenance and generation-job history may remain with library data.
- Sample sources retain their own attribution and licenses; the app code license does not relicense sample content.
- New imports and generated results require explicit review before becoming library items.
