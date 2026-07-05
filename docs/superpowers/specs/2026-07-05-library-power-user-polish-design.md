# Library Power-User Polish Design Spec

## Goal

Improve the daily management experience for large local Image Prompt Library collections by making search, sort, filter state, cleanup, and batch organization safer and more visible.

This milestone focuses on the core library surface before adding more onboarding, generation, or external-import work.

## Decision Context

The roadmap decision from `G:\Codex\jarvis-state\decisions\2026-07-05-image-prompt-library-roadmap.md` keeps four product-improvement lanes active:

- Install and onboarding hardening.
- Library power-user polish.
- Generation workflow hardening.
- External inspiration ingestion.

The recommended next implementation milestone is Library Power-User Polish because the library surface is the core product experience. Better browsing, finding, cleaning, and organizing reduces daily-use friction before adding more users, generated outputs, or imported references.

## Non-Goals

- Do not start account management.
- Do not add URL, X/Threads, Instagram, or broad external import workflows.
- Do not add new generation provider capabilities or arbitrary image-size controls.
- Do not redesign Cards or Explore from scratch.
- Do not introduce a full query language with OR, parentheses, saved searches, or nested filters.
- Do not remove or flatten generation/import provenance.

## Product Scope

### 1. Search and Filter Clarity

Plain keyword search must continue to work as it does today: users can search across item titles, prompt text, tags, collections, sources, and notes.

Add lightweight structured query support for common power-user filtering:

- `created:today`
- `created:yesterday`
- `created:7d`
- `created:30d`
- `updated:today`
- `updated:yesterday`
- `updated:7d`
- `updated:30d`
- `tag:<text>`
- `collection:<text>`
- `model:<text>`
- `source:<text>`
- `fav:true`
- `fav:false`
- `has:image`
- `has:result`
- `has:reference`
- `has:prompt`

Rules:

- Supported `key:value` tokens become structured filters.
- Remaining text stays as normal keyword search.
- Filters and keywords combine with AND semantics.
- Unknown `key:value` tokens remain normal keyword text.
- Commas may separate tokens but are not required.
- Query parsing should be shared or mirrored predictably between backend behavior and frontend chip display.

Examples:

- `apple` searches normally.
- `created:7d apple` finds recently created items matching `apple`.
- `tag:template source:awesome packaging` finds matching template items from a source containing `awesome`.
- `creator:edward apple` remains a plain keyword search because `creator` is unsupported.

### 2. Visible Sort Control

Add a visible sort control near the search/status area.

Supported sort modes:

- `updated_desc` - Recently updated, default.
- `created_desc` - Recently added.
- `created_asc` - Oldest added.
- `title_asc` - Title A-Z.
- `title_desc` - Title Z-A.
- `source_asc` - Source.
- `model_asc` - Model.

Existing `sort:title`, `sort:created`, and `sort:updated` search tokens may continue to work for compatibility, but the visible control should be the preferred UI.

### 3. Active State Visibility

Show compact active-state chips for:

- Keyword search.
- Collection filter.
- Structured query filters.
- Sort mode when not default.

Each chip should make it clear what is active. Clearing should be easy:

- Search can be cleared from the search input.
- Collection chip can clear the selected collection.
- Sort chip/menu can reset to default.
- Structured filter chips may be removable in the first implementation if the change remains small; otherwise display-only is acceptable for the first slice as long as clearing the search field clears them.

### 4. Batch Management

Improve the existing Cards selection mode into a focused batch-management workflow.

Batch actions:

- Delete selected items.
- Archive selected items.
- Unarchive selected items.
- Favorite selected items.
- Unfavorite selected items.
- Add tags to selected items.
- Remove tags from selected items.
- Move selected items to a collection.

Backend should provide batch endpoints instead of relying on many frontend per-item mutation calls.

Batch action requirements:

- Work only in local mutable mode.
- Remain unavailable in the GitHub Pages demo.
- Confirm destructive actions.
- Return clear counts: requested, changed, skipped, and failed.
- Refresh item list, clusters, and tags after success.
- Preserve provenance fields on items.

### 5. Cleanup

Add conservative local cleanup support for image records and media files.

Cleanup should be preview-first.

Preview categories:

- Image records whose referenced files are missing.
- Files under known library media directories that are not referenced by any image record.
- Stale generation staging files are out of the first cleanup apply scope unless the implementation plan can prove they are unreferenced through existing job and accepted-item records.

Apply categories:

- Remove broken image records.
- Remove unreferenced media files.
- Do not delete generation staging files in the first implementation unless they are included in the preview with a traceable database reason.

Safety rules:

- Never delete outside the configured library path.
- Only inspect known media/staging directories.
- Do not follow unsafe symlinks.
- Do not use broad recursive deletion behavior from the UI.
- Apply only items returned by the preview.
- Show counts before and after cleanup.

### 6. Archive/Delete Confidence

Clarify destructive and semi-destructive flows:

- Delete confirmation should state that library records are deleted and unreferenced local image files may also be removed.
- Archive should be positioned as reversible cleanup.
- Batch delete should be visually distinct from archive.
- Empty collections should continue to be cleaned up after delete/archive where existing behavior supports it.

### 7. Provenance and Metadata Cleanliness

Do not remove generation/import provenance.

Power-user cleanup should make saved items easier to manage without losing:

- `source_name`
- `source_url`
- Generation source item metadata.
- Generation job provenance.
- Prompt provenance.
- Model/source metadata.

This milestone may expose provenance more clearly in detail/edit surfaces only if needed for cleanup confidence. It should not add a broad metadata migration.

## Technical Shape

### Backend

Expected additions:

- `backend/services/search_query.py`
- Batch mutation schemas in `backend/schemas.py`
- Batch item mutation methods in `backend/repositories.py`
- Batch routes in `backend/routers/items.py`
- Cleanup service, likely `backend/services/library_cleanup.py`
- Cleanup router, likely `backend/routers/cleanup.py`

Existing APIs must remain compatible.

### Frontend

Expected additions and changes:

- Extend `frontend/src/utils/searchSort.ts`.
- Extend `frontend/src/types.ts`.
- Extend `frontend/src/api/client.ts`.
- Update `frontend/src/hooks/useItemsQuery.ts`.
- Update `frontend/src/components/TopBar.tsx`.
- Update `frontend/src/App.tsx`.
- Add or update batch action UI in the selection toolbar.
- Add cleanup panel inside local Config/management UI.

### Demo Mode

The static GitHub Pages demo should support read-only search/sort/filter behavior where the static data path can do so without adding mutation behavior.

All cleanup and batch mutation controls must remain hidden or disabled in demo mode.

## Acceptance Criteria

- Plain search behavior remains unchanged.
- Supported structured filters narrow results correctly.
- Unsupported query tokens do not break search.
- Sort can be changed through visible UI.
- Active search/filter/sort state is visible.
- Batch delete/archive/favorite/tag/collection actions operate through backend batch APIs.
- Cleanup preview performs no deletion.
- Cleanup apply only removes previewed safe records/files.
- Public demo remains read-only.
- Existing generation/import provenance remains intact.

## Verification Plan

Backend:

- Add parser tests for structured search queries.
- Add API tests for structured filtering and sort modes.
- Add API tests for batch actions.
- Add cleanup preview/apply tests with safe temporary library fixtures.
- Run focused item/image tests.

Frontend:

- Add or update static tests for visible sort control, active chips, local-only batch controls, and cleanup UI.
- Run frontend build.

Regression:

- Existing item API tests pass.
- Existing image-store tests pass.
- Existing public demo/read-only tests pass.

## Implementation Choices To Resolve In Plan

These choices should be resolved in the implementation plan:

- Whether structured filter chips are removable in the first implementation or display-only.
- Whether cleanup lives in the existing Config drawer or a small dedicated management panel opened from Config.
- Whether stale generation staging cleanup has enough existing database references to include safely; if not, defer it.
