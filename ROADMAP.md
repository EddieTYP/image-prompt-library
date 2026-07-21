# Roadmap

## Current stable direction

Image Prompt Library is a local-first prompt and image manager. The current stable release is `v0.8.2`; its public GitHub Pages demo is a static, read-only catalogue of attributed prompt/image references. Private-library management, local data, and optional ChatGPT / Codex OAuth generation remain local-install features. The application code is AGPL-3.0-or-later, with commercial licensing available for organizations that need different terms.

The project does not provide hosted accounts, checkout, payments, SaaS sync, or a hosted private library. SQLite data, images, prompts, and provider state stay on the user's machine.

## Roadmap lanes

The roadmap uses four product lanes. They are ongoing areas, not four sequential releases. Each lane records what is already shipped; all near-term planned work is consolidated in the prioritized list below.

### A. Install and onboarding hardening — current milestone complete

Native Windows Quick Start shipped in `v0.8.0`, including versioned installs, background lifecycle commands, diagnostics, transactional updates, release assets, and rollback.

Published download/install verification, Windows handled-failure recovery, source and release update UI, and macOS launchd lifecycle support are complete. POSIX update/rollback resilience, handled-interruption recovery, release gates, and exact `v0.8.0` rollback compatibility shipped through `v0.8.2`. Further installer work should respond to observed failures rather than reopen this milestone broadly.

### B. Library power-user polish — current milestone complete

The completed milestone added clearer search, sort, and filter state; backend-backed batch management; preview-first cleanup; and stronger metadata/provenance handling.

Any future library work should be driven by observed usability problems rather than reopening this milestone broadly.

### C. Generation workflow hardening — current milestone complete on `main`

The generation foundation, OAuth connection flow, queued jobs, result review, attach/save-as-new actions, retry controls, and session-reliability hardening are shipped.

The focused Generation Input & Reference Polish milestone is complete. Generation now supports ordered uploaded, saved-library, and prior-result references with preserved provenance across retry, review, attach, and save-as-new flows on desktop and mobile.

Manual retry, stalled-job recovery, provider-failure classification and guidance, backend-restart recovery, and the credential-path boundary are complete. OAuth credentials and session configuration are app-owned outside the library by default, and current backup, sample, and demo paths omit them.

Post-`v0.8.2` work on `main` adds atomic Generation sets of 1, 3, 5, or 10 jobs, exact queue progress, a production concurrency cap of five, provider pause/backoff handling, and individual review/retry semantics. These changes are merged but are not part of the current stable release until the next release is published.

### D. External inspiration import — deferred

Local markdown repository ingestion and the shared `ImportDraft` review flow remain available. Generic URL plus X/Threads import, along with Instagram adapters, remains deferred because reliable social-post reply extraction requires platform authentication, paid APIs, or brittle scraping that does not yet meet the product's acceptance bar.

If this lane resumes, adapters must still feed candidate prompts, media, provenance, warnings, and duplicate checks into `ImportDraft` for explicit user confirmation before library writes.

## Prioritized outstanding work

1. **Portable backup and safe restore — `v0.9.0` release milestone** — replace the former partial, operator-managed archive procedure with a validated export/import contract. Preserve credentials and session data outside the archive; cover accepted library media plus required generation data; reject unsafe archive paths and links; validate before mutation; and preserve the original library if restore fails.
2. **Explore clarity — required before `v1.0.0`** — replace the constellation with a two-level desktop/mobile discovery flow based on existing Collections. With no active collection or search, Explore shows a normal-scroll directory of non-empty Collections using existing localized names, counts, and preview images without cropping source images. Selecting a Collection keeps the user in Explore, applies the existing collection filter state, and opens a natural-ratio image feed; an active search shows the matching Explore feed, and clearing the search or collection returns to the directory with prior state preserved. Reuse existing collection, filter, item-detail, and image-ratio data; do not add a new taxonomy or library data model. When this revamp ships, rename the visible `Cards` mode to `Library`. Explore item detail keeps Copy, Download, Generate, and Edit, but does not expose selection or batch management; full management remains in Library.
3. **Colour themes — separate visual milestone** — add two browser-local light palettes: the current warm appearance as `Canvas Light`, and the G/H-inspired neutral-blue appearance as `Studio Light`. Use semantic colour tokens, accessible contrast, and the same preference in local installs and the static demo. Keep this separate from the Explore interaction change; dark mode and system-theme following remain out of scope until separately approved.
4. **Library batch UX quick wins (B)** — add a concise batch `Tag` tooltip and replace the batch `Move` free-text collection prompt with an existing-collection selector. This is independent patch-sized work and may ship between larger milestones.
5. **Library multi-image management** — generation already supports ordered multi-image inputs. After safe restore is available, add item-level controls to delete, reorder, and change image role or primary selection without duplicating generation reference controls.

The former responsive vertical-constellation follow-up is superseded by Explore clarity and should not be implemented as a second browsing model.

## Planned update sequence

These are product and release groups, not promised version numbers. Small independent fixes may ship between them when they do not broaden the main milestone.

1. **Data safety and `v0.9.0` release closure** — finish Portable backup and safe restore, then cut `v0.9.0` with both the already-merged post-`v0.8.2` Generation-set work and the new recovery contract. Require cross-platform restore regression coverage, the existing generation queue/concurrency checks, and a release gate appropriate to data replacement.
2. **Explore clarity** — ship the Collections directory and natural-ratio Explore feed together on desktop, mobile, and GitHub Pages. Preserve search/filter/detail state and keep the static demo read-only. This is the required browsing revamp before `v1.0.0`.
3. **Colour themes** — establish the semantic token boundary and ship `Canvas Light` plus `Studio Light` as a separate, fully regression-tested visual update after the Explore interaction has settled.
4. **Library management follow-ups** — take the batch `Tag`/`Move` quick wins as a small patch, then scope multi-image delete/reorder/role/primary management against the shipped restore boundary. Multi-image management should not hold `v1.0.0` if its data-integrity scope is not ready.
5. **`v1.0.0` readiness** — run final Windows and POSIX install/update/rollback/restore checks, desktop/mobile and static-demo QA, migration and privacy checks, and documentation alignment. Do not use the `v1.0.0` release gate to introduce a new provider, import architecture, account system, or other unrelated feature.

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
