# Roadmap

## Current stable direction

Image Prompt Library is a local-first prompt and image manager. The current stable release is `v0.8.0`; its public GitHub Pages demo is a static, read-only catalogue of attributed prompt/image references. Private-library management, local data, and optional ChatGPT / Codex OAuth generation remain local-install features. The application code is AGPL-3.0-or-later, with commercial licensing available for organizations that need different terms.

The project does not provide hosted accounts, checkout, payments, SaaS sync, or a hosted private library. SQLite data, images, prompts, and provider state stay on the user's machine.

## Roadmap lanes

The roadmap uses four product lanes. They are ongoing areas, not four sequential releases.

### A. Install and onboarding hardening — active follow-up

Native Windows Quick Start shipped in `v0.8.0`, including versioned installs, background lifecycle commands, diagnostics, transactional updates, release assets, and rollback.

Outstanding:

- Continue release-download, interrupted-update, recovery, and rollback QA.
- Harden service and update resilience beyond the current Windows background controller.

### B. Library power-user polish — current milestone complete

The completed milestone added clearer search, sort, and filter state; backend-backed batch management; preview-first cleanup; and stronger metadata/provenance handling.

Any future library work should be driven by observed usability problems rather than reopening this milestone broadly.

Observed UX follow-ups:

- Add a concise tooltip to batch `Tag` explaining that it adds tags to every selected item and how to enter multiple tags.
- Replace the batch `Move` free-text collection prompt with a dropdown of existing collections.

### C. Generation workflow hardening — active follow-up

The generation foundation, OAuth connection flow, queued jobs, result review, attach/save-as-new actions, retry controls, and session-reliability hardening are shipped.

The focused Generation Input & Reference Polish milestone is complete. Generation now supports ordered uploaded, saved-library, and prior-result references with preserved provenance across retry, review, attach, and save-as-new flows on desktop and mobile.

Outstanding:

- Improve retry and provider-error recovery where current guidance is still weak.
- Keep credentials and provider state outside libraries, backups, samples, and public demo data.

### D. External inspiration import — deferred

Local markdown repository ingestion and the shared `ImportDraft` review flow remain available. Generic URL, X/Threads, and Instagram adapters are deferred because reliable social-post reply extraction requires platform authentication, paid APIs, or brittle scraping that does not yet meet the product's acceptance bar.

If this lane resumes, adapters must still feed candidate prompts, media, provenance, warnings, and duplicate checks into `ImportDraft` for explicit user confirmation before library writes.

## Prioritized outstanding work

1. **Release and update resilience** — complete lane A follow-up QA and recovery hardening.
2. **Generation workflow polish** — continue focused retry and provider-error recovery improvements.
3. **Mobile browsing polish** — improve Cards density, detail/drawer layouts, and contained Explore gestures with a vertical constellation layout.
4. **Batch image editing** — improve multi-image management without reopening the completed library-polish milestone.
5. **Backup archive UI** — add optional export/import of a portable local backup archive.

## Later or optional work

- Additional sample/demo packs and a fuller interface language setting.
- Optional semantic/vector search after normal search proves insufficient.
- Optional local accounts with password-capable admin/editor/read-only roles and shared/private visibility.

Account work must preserve the local-first model: backend permissions protect app workflows, OS filesystem permissions protect the raw vault, existing items remain shared during migration, and GitHub Pages stays account-free and read-only.

## Product constraints

- Public GitHub Pages remains a multilingual, provenance-aware, read-only demo.
- Add, edit, generation, private-library management, and provider authentication remain local-install features.
- Sample sources retain their own attribution and licenses; the app code license does not relicense sample content.
- New imports and generated results require explicit review before becoming library items.
