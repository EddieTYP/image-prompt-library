# Roadmap

## Current stable direction

Image Prompt Library is a local-first prompt and image manager. The current stable release is `v0.7.10`; its public GitHub Pages demo is a static, read-only catalogue of attributed prompt/image references. Private-library management, local data, and optional ChatGPT / Codex OAuth generation remain local-install features. The application code is AGPL-3.0-or-later, with commercial licensing available for organizations that need different terms.

The project does not provide hosted accounts, checkout, payments, SaaS sync, or a hosted private library. The local-first model keeps the SQLite database, images, prompts, and provider state on the user's machine.

## v0.8.0 release focus

Native Windows Quick Start is the unreleased v0.8.0 focus. It prepares a PowerShell installer for Windows 10/11 with Python 3.10+, versioned app state under the user profile, a separate private library, background lifecycle commands, diagnostics, verified release assets, transactional update recovery, and rollback. v0.7.10 remains the current stable release until v0.8.0 is released.

Release follow-up remains necessary for service and update resilience beyond the Windows background controller, including continued release-download and recovery QA.

## Product follow-ups

- Improve batch image editing and import-review workflows.
- Continue richer generation retry, saved-reference, and input-image UX.
- Continue mobile Explore gestures and vertical layout improvements.
- Build **Generic URL plus X/Threads import** through the existing reviewable ImportDraft flow, then consider Instagram as a later experimental adapter.
- Add an optional export/import backup archive UI.
- Consider additional sample/demo packs, a fuller interface language setting, and optional semantic/vector search.

## Local generation

Optional local generation keeps provider authentication and state outside the private library, backups, sample bundles, and public demo data. Users can connect a provider, create queued jobs, review results, attach results to an item, or save a result as a new item. Future work should preserve that explicit review step and improve retry, error handling, saved references, and input-image support without exposing private credentials.

## Read-only demo and provenance

The public site remains a multilingual, provenance-aware read-only demo. Visitors can browse, search, inspect prompts and images, switch UI language, and copy public sample prompts. Add/edit/private-library management stays in local installs. Sample sources retain their own attribution and licenses; the app code license does not relicense sample content.

Mobile browsing remains in scope: Cards should stay touch-first, and Explore should become a contained mobile canvas with one-finger pan, two-finger pinch zoom, and a vertical constellation layout.

## Account-management direction

Future local account management may add optional password-capable accounts, admin/editor/read-only roles, and shared/private item visibility. Any account work must preserve the local-first model: backend permission checks protect app workflows, raw vault protection relies on OS filesystem permissions, existing items remain shared during migration, and GitHub Pages stays account-free and read-only.

## Import direction

Importers should remain local-first and user-confirmed. Source adapters feed the common ImportDraft review flow with source metadata, candidate prompts/images, provenance, warnings, and duplicate checks before writing to the library. The intended order is local repository ingestion, Generic URL plus X/Threads import, then Instagram only after those adapters prove useful.
