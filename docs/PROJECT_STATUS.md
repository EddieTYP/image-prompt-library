# Image Prompt Library Project Status

Last updated: 2026-04-25

## Current direction

The app has two distinct browsing modes:

1. **Explore mode = thumbnail constellation graph**
   - Similar to an Obsidian graph-view mental model, but with visual cards: cluster cards are hub nodes and image thumbnails are connected item nodes.
   - It must keep real **cluster cards** and real **image thumbnails**; do not degrade the main Explore experience into abstract dots.
   - Global Explore should show multiple cluster-card constellations with a configurable overall thumbnail budget, not a fixed per-cluster thumbnail count.
   - Focus Explore should center the selected cluster card and let image thumbnails radiate outward in a stable, collision-aware constellation.
   - This is a knowledge-map / galaxy browsing mode, not a normal grid and not one card per cluster.

2. **Cards mode = masonry/template marketplace browsing**
   - Keep the masonry/Pinterest/Vista-style feature.
   - Make the layout adaptive by viewport width so desktop can show more columns without losing masonry density.
   - Cards should support hover/action affordances.

## Confirmed product decisions

- No hero section. The top search bar is enough.
- Keep the top toolbar search, logo area, filters entry, config entry, and floating Add button.
- Keep the active filter/status strip and visible count, but continue polishing its wording and appearance.
- No `⌘K` / `Ctrl+K` search shortcut for now; it was removed from the plan.
- The current logo section size is acceptable; replace the placeholder with a real logo later.
- Detail modal and edit modal are much better after the polish pass, but can continue to improve.
- Cards mode masonry is now restored and visually acceptable.
- Future UI must preserve first-class actions:
  - Copy prompt
  - Favorite
  - Edit

## Current implementation checkpoints

Committed checkpoints:

- `16fe431 Polish toolbar and modal planning checkpoint`
- `214fe6a Implement orbit explore and masonry cards`
- `732d52f Fix prompt copy language preference`
- `3c1fcc1 Avoid Hermes WebUI port for app dev server`
- `a95b7ad Fix copy prompt on LAN HTTP`
- `8f46c69 Polish explore orbit focus mode`

Current state after `8f46c69`:

- Explore currently uses a spatial pan/zoom orbit map with cluster labels and ring/lane item nodes.
- Batch 2 added dot LOD, focus mode, inactive cluster fade, and an **Open as Cards** CTA, but user feedback showed the direction is not yet right:
  - Default Explore still feels visually packed together.
  - Dot LOD is not acceptable as the main Explore representation because the user wants real image thumbnails.
  - Focus mode still reads as a messy ring/wreath rather than thumbnails radiating from a cluster card.
  - Cluster click can feel unreliable because normal `onClick` is mixed with pan/drag gestures.
- Next Explore direction is to replace the ring/orbit layout with a **thumbnail constellation graph**:
  - cluster cards remain visible hub nodes
  - image thumbnails remain image cards
  - thumbnails connect/radiate from their cluster card
  - layout is stable/deterministic after calculation, not continuously animated
  - visible item counts are controlled by configurable caps/budgets
- Cards mode uses adaptive masonry via CSS columns.
- Card hover actions exist for Copy prompt, Favorite, and Edit.
- Batch 1 is complete and committed:
  - Card-level Copy prompt uses full prompt text from item summaries, not `prompt_snippet || title`.
  - Config panel supports preferred prompt copy language: Traditional Chinese, Simplified Chinese, and English.
  - Current code values are normalized as `zh_hant`, `zh_hans`, and `en`.
  - Default preferred language is Traditional Chinese (`zh_hant`).
  - Shared resolver fallback order is preferred language → English → any available prompt → title.
  - Detail modal copy copies the currently selected/visible prompt tab first, then falls back to the shared resolver.
  - Copy prompt now uses a shared clipboard helper with a textarea/`execCommand('copy')` fallback so LAN HTTP testing works even when `navigator.clipboard` is unavailable.
- Development port convention is now explicit:
  - Backend API uses `127.0.0.1:8000`.
  - Vite frontend uses `127.0.0.1:5177`.
  - Do not use `8787`; it is reserved for Hermes WebUI.
- Batch 1 verification passed:
  - `.venv/bin/python -m pytest -q` → `21 passed`.
  - `npm run build` → passed.
  - Backend `py_compile` → passed.
  - Browser QA verified card copy for Traditional/Simplified/English/fallback and detail-modal selected-tab copy.
  - Independent review passed after fixing the detail-modal selected-tab copy mismatch.

- Batch 2 verification passed:
  - `.venv/bin/python -m pytest -q` → `23 passed`.
  - `npm run build` → passed.
  - Browser QA on LAN verified global dot LOD readability, focused cluster panel/CTA, inactive cluster fade, ordered preview rings, Cards CTA switching, and a clean console.
  - Independent review approved with no critical or important issues.

Known issues / next Explore target:

- Copy prompt language preference and LAN HTTP clipboard fallback are now fixed; remaining copy UX polish could add visible copied/error feedback later.
- Batch 3 thumbnail constellation graph is implemented and committed as `520a2da Implement explore thumbnail constellation graph`:
  - no dot-only main representation
  - configurable global and focus thumbnail budgets
  - stable cluster-card + image-thumbnail graph layout
  - reliable tap-vs-drag interaction handling
  - preserve Cards mode and existing copy/favorite/edit actions.
- Next refinement: add **static post-layout repulsion relaxation** for image cards. The current layout uses one-pass collision-aware spiral placement, which reduces overlap but can still leave dense focus-mode thumbnails stuck together. Preferred Option A is to keep the deterministic/static layout, then run a bounded relaxation pass where thumbnail nodes repel other thumbnail nodes and cluster hub boxes, while a light spring pulls each thumbnail back toward its owning cluster. The result should settle once and remain static; do not introduce continuous live physics/jitter unless explicitly requested later.

## Explore thumbnail constellation requirements

### Core layout

- Explore should use a thumbnail constellation graph metaphor, similar to Obsidian graph view in structure but **not** in visual abstraction.
- Cluster cards are hub nodes with readable name/count/overflow metadata.
- Image/item nodes are real image thumbnails, not dots, and should visually connect or radiate from their owning cluster card.
- Global Explore should show many cluster-card constellations across a large pan/zoom canvas.
- Focus Explore should center the selected cluster card and arrange that cluster's visible thumbnails outward in a stable, collision-aware constellation.
- Avoid the current messy circular wreath/ring look. Thumbnails should feel like they radiate from the cluster card along natural graph-like spokes or force-like separation.
- The layout may calculate once on load/focus and then stay static. Continuous physics animation is not required and should be avoided unless explicitly desired later.

### Interaction

- Pan the canvas.
- Wheel/pinch zoom the canvas.
- Reset view.
- Tap/click an image thumbnail to open the detail modal.
- Search/filter should hide or de-emphasize non-matching thumbnails.
- Cluster/item activation should use a tap-vs-drag threshold so slight pointer movement does not make cluster click/focus feel unreliable.

### Cluster click/focus behavior

Preferred direction:

- **Single click cluster = focus that cluster inside Explore**, not immediately switch to Cards.
- Focus mode should preserve the Explore/galaxy mental model.
- Focused cluster should expand to occupy most of the map viewport.
- Other clusters/items should fade out or hide while focused.
- User can return to global Explore by:
  - zooming out / reset / back-to-map control, and later possibly `Esc`
  - clearing active cluster filter/status chip
- Focus mode should include an explicit CTA such as **Open as Cards** for deep browsing in filtered Cards mode.

Rationale:

- Explore is for visual/spatial browsing; Cards is for deep browsing.
- Directly switching to Cards on cluster click would make Explore feel like a category menu instead of a map.
- A focus mode lets users inspect one cluster visually before deciding whether to open the full filtered masonry list.

### Visible thumbnail budgets / caps

Showing every image thumbnail globally is not practical for usability or performance, but the main Explore representation should still use thumbnails rather than dots.

Planned cap model:

- Global Explore uses an **overall configurable thumbnail budget**, not a fixed per-cluster cap.
- Default global thumbnail budget: `100` total thumbnails across all clusters.
- Global allocation should preserve small clusters and still reflect large-cluster scale:
  1. Give each non-empty cluster a small minimum allocation first, e.g. `min(2, cluster item count)`.
  2. Allocate remaining global budget proportionally by cluster size / visible matched item count.
  3. Apply a soft per-cluster maximum if needed to prevent a very large cluster from dominating the overview.
- Focus Explore uses a **configurable focus thumbnail budget**.
- Focus budget target/default can be `100` if the layout stays readable; otherwise keep the setting available and tune the default after browser QA.
- The UI should expose caps in Config, initially as simple settings:
  - `Global thumbnail budget` (for example `50 / 75 / 100 / 150`)
  - `Focus thumbnail budget` (for example `24 / 48 / 72 / 100`)
- Budget settings can be localStorage/frontend config first; backend-persisted config can come later.
- Cluster cards should show total cluster count and hidden overflow such as `+67 more`.

### Node prioritization

Current priority order:

1. Favorite items first.
2. User rating.
3. Items with usable thumbnails/previews.
4. Stable deterministic title ordering.

Future scoring/ranking system can replace this without redesigning the UI.

### Thumbnail level-of-detail / performance

Explore should preserve real thumbnails as the main visual representation.

- **Global Explore**:
  - Render real thumbnail cards using `thumb_path` within the global thumbnail budget.
  - Do not use dot-only LOD as the primary default view.
  - Avoid original images.
- **Focus Explore**:
  - Render real thumbnail cards within the focus budget.
  - Prefer `thumb_path` for the first implementation if focus cap is high (`100`), then consider `preview_path` selectively for hovered/selected/larger cards.
  - Avoid original images.
- **Detail modal / explicit high-res view only**:
  - Use `original_path`.

Implementation notes:

- Add a single image source resolver for Explore thumbnail nodes, e.g. `getExploreThumbnailPath(item, mode)`.
- Avoid fallback to `original_path` in Explore.
- Use `loading="lazy"`, `decoding="async"`, capped DOM counts, and lightweight shadows/filters.
- Browser QA should check smooth pan/zoom, focus transition readability, image loading behavior, and console cleanliness.

## Cards masonry requirements

- Keep masonry layout; do not replace it with a plain equal-row grid.
- Make masonry adaptive by viewport width.
- Preserve template-marketplace density and visual browsing feel.
- Keep action affordances available on cards: copy prompt, favorite, edit/open.
- Current Cards mode is visually acceptable and should not be destabilized while working on Explore.

## Copy prompt / language preference behavior

Status: implemented in Batch 1 and committed as `732d52f`.

Current behavior:

- Config lets the user choose preferred prompt language:
  - Traditional Chinese: `zh_hant`
  - Simplified Chinese: `zh_hans`
  - English: `en`
- Card Copy prompt resolves prompt text in this order:
  1. Preferred language prompt.
  2. English prompt.
  3. Any available full prompt.
  4. Title only as final fallback.
- Detail modal shows language tabs and copies the currently selected/visible prompt first.
- Detail modal falls back to the shared resolver if the selected tab has no prompt.
- The resolver works with normalized Traditional Chinese prompts generated during import/create/update.

Implementation options to inspect:

- Add prompt data or a precomputed preferred prompt field to item summaries returned by `/api/items`.
- Keep full prompts on item detail endpoint for modal.
- Add frontend config state/API for preferred language.
- Ensure copy action uses the shared clipboard helper. It should try the async Clipboard API first, then fall back to textarea selection plus `document.execCommand('copy')` for LAN HTTP origins where `navigator.clipboard` is unavailable.

## Next implementation plan

Implement in two commits/batches rather than one large mixed change.

### Batch 1 — functional correctness: copy prompt language preference — completed

Goal: fix Copy prompt before deeper visual work.

Status: completed and committed as `732d52f Fix prompt copy language preference`.

Tasks:

1. Inspect current config API/state and item summary/detail prompt data.
2. Add/update tests first:
   - prompt language resolver chooses preferred language
   - fallback to English
   - fallback to any prompt
   - card copy no longer uses snippet/title when full prompt exists
3. Add preferred prompt language config:
   - `zh-Hant`, `zh-Hans`, `en`
   - default should likely be `zh-Hant` for Edward's workflow.
4. Expose enough prompt text to Cards view to copy the correct full prompt.
5. Make Card and Detail modal use the same prompt resolver.
6. Verify:
   - `.venv/bin/python -m pytest -q`
   - `npm run build`
   - browser test card copy behavior and modal copy behavior.
7. Commit as a standalone functional fix.

### Batch 2 — Explore orbit UX/performance — completed

Goal: make Explore feel like an ordered orbit map, not a cluttered scatter plot.

Status: completed in the current Batch 2 commit.

Tasks completed:

1. Refactored orbit layout into deterministic cluster-local geometry:
   - cluster center
   - label exclusion zone
   - ring/lane placement
   - stable angular ordering
2. Added focus mode:
   - click cluster to focus inside Explore
   - focused cluster occupies the map center
   - non-focused clusters fade and their item nodes are hidden
   - Reset returns the view/camera to the default map framing
   - Open as Cards CTA switches to Cards with the focused cluster filter
3. Added adaptive image level-of-detail:
   - far/default: dots, no image requests
   - mid: thumbnails
   - near/focused: previews
   - modal only: original
4. Kept node caps:
   - global default `12`
   - focused cluster `24`
5. Added static guards:
   - focus mode remains in map
   - Open as Cards CTA exists
   - orbit image resolver avoids original paths
   - LOD-related code/classes exist
6. Verified:
   - `.venv/bin/python -m pytest -q` → `23 passed`
   - `npm run build` → passed
   - browser visual QA for global Explore, focused cluster, Cards CTA, and console errors.
7. Independent review approved before committing.

### Batch 3 — Explore thumbnail constellation graph — planned

Goal: replace the current ring/dot orbit implementation with a stable thumbnail graph that keeps cluster cards and image thumbnails as first-class visuals.

Requirements:

1. Preserve visual node types:
   - Cluster card = hub node with name/count/hidden overflow.
   - Image item = thumbnail card, not dot.
2. Global Explore:
   - Use an overall configurable thumbnail budget, default `100`.
   - Allocate budget across clusters with a minimum for small clusters and proportional distribution for large clusters.
   - Spread cluster-card constellations across the canvas; avoid the current compressed central blob.
3. Focus Explore:
   - Click/tap a cluster to focus inside Explore.
   - Center the selected cluster card.
   - Show up to configurable focus budget, target/default `100` if browser QA stays readable.
   - Arrange thumbnails as a graph-like constellation radiating from the cluster card, with collision avoidance and minimal overlap.
   - The layout can calculate once on focus and then remain static; no continuous physics/jitter required.
   - Keep **Open as Cards** CTA for deep browsing in Cards mode.
4. Config:
   - Add Config controls for `Global thumbnail budget` and `Focus thumbnail budget`.
   - Frontend/localStorage persistence is acceptable for the first version.
5. Interaction:
   - Implement tap-vs-drag threshold so cluster focus and item open feel like normal clicks inside a pannable canvas.
   - Pan/zoom/reset should continue to work.
6. Media/performance:
   - Use `thumb_path` for Explore thumbnails initially, especially when caps are high.
   - Do not use `original_path` in Explore.
   - Keep modal/detail as the high-res path.
7. Verification:
   - Add/update static guards for thumbnail graph direction, configurable caps, no dot-only default, no original-path Explore fallback, and tap-vs-drag threshold.
   - Run `.venv/bin/python -m pytest -q` and `npm run build`.
   - Browser QA on LAN: default global readability, focus readability/overlap, click reliability, Cards unchanged, console clean.
   - Run independent review before commit.

## Future scoring system idea

A future item score can combine:

- manual favorite/pin status
- user rating
- source quality
- prompt completeness
- image quality/representativeness
- usage frequency or copy count
- recency, if desired

The orbit map should be designed so the ranking source can be swapped later without redesigning the UI.

## Verification checklist for future UI passes

- `.venv/bin/python -m pytest -q`
- `npm run build`
- Browser console has no JS errors.
- Explore global map loads and is readable.
- Explore focused cluster mode works and can return to global map.
- Cards masonry still looks correct.
- Detail modal opens from both Explore and Cards.
- Copy prompt uses preferred language and full prompt, not snippet/title.
- Favorite and Edit still work.
- No runtime media/database artifacts are committed.
