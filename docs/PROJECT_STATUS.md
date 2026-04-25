# Image Prompt Library Project Status

Last updated: 2026-04-25

## Current direction

The app has two distinct browsing modes:

1. **Explore mode = spatial orbit map**
   - Similar to the previous OpenNana `html-gallery` experience.
   - Cluster labels are visible anchors on a large pan/zoom canvas.
   - Image/item thumbnails should orbit around cluster names in an ordered way, not scatter randomly.
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

Current state after `214fe6a`:

- Explore is a spatial pan/zoom orbit map with cluster labels and image nodes.
- Default visible nodes per cluster: `12`.
- Focused cluster cap: `24`.
- Node priority: favorite first, then rating, then image availability, then deterministic title order.
- Cards mode uses adaptive masonry via CSS columns.
- Card hover actions exist for Copy prompt, Favorite, and Edit.

Known issues from review:

- Explore images still feel visually cluttered and not sufficiently ordered around clusters.
- Orbit map performance can feel weak when many image nodes are displayed.
- Explore node image source currently resolves `thumb_path → preview_path → original_path`; original is only used as fallback, but map should avoid using original images in normal browsing.
- Copy prompt action is functionally wrong: it currently copies `prompt_snippet || title`, not the full prompt in the desired language.

## Explore orbit map requirements

### Core layout

- Cluster labels should be rendered as in-canvas anchors with name and count.
- Image/item nodes should be positioned around the relevant cluster label in ordered rings/lanes.
- The user should be able to visually understand cluster scale and topic neighborhoods.
- Avoid random-looking scatter. Each cluster should have clear local structure:
  - center label / cluster card
  - exclusion zone around the label
  - one or more orbit rings
  - stable lane assignment for item nodes
  - reduced overlap between thumbnails

### Interaction

- Pan the canvas.
- Wheel/pinch zoom the canvas.
- Reset view.
- Click an image node to open the detail modal.
- Search/filter should hide or de-emphasize non-matching nodes.

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

### Maximum visible nodes per cluster

Showing every item around every cluster is not practical for usability or performance.

Current baseline:

- Default max visible nodes per cluster: `12`.
- Focused cluster max visible nodes: `24`.
- Tiny clusters can show all items if count is below the cap.
- The cluster label should show the total cluster count.
- If a cluster has hidden overflow, show a subtle indicator such as `+67 more`.

Future tuning:

- Focused cluster could increase to `36` or `48` once layout/performance is improved.
- Very zoomed-out mode may show fewer than `12`, or use dots/collage instead of full thumbnails.

### Node prioritization

Current priority order:

1. Favorite items first.
2. User rating.
3. Items with usable thumbnails/previews.
4. Stable deterministic title ordering.

Future scoring/ranking system can replace this without redesigning the UI.

### Adaptive image level-of-detail / performance

Implement seamless adaptive display based on zoom/focus distance:

- **Far / global zoomed-out**:
  - Use tiny thumbnails, abstract dots, or mini-collage badges.
  - Avoid rendering many large images.
  - Do not use original images.
- **Mid zoom**:
  - Use `thumb_path` images.
  - Show more item shape/detail but keep node count capped.
- **Near / focused cluster**:
  - Use `preview_path` for larger visible nodes if available.
  - Increase representative node cap after performance is acceptable.
- **Detail modal / explicit high-res view only**:
  - Use `original_path`.

Implementation notes:

- Add a single image source resolver for map nodes, e.g. `getOrbitImagePath(item, zoomLevel, focused)`.
- Avoid fallback to `original_path` in the map except as a last resort or placeholder case.
- Consider lazy loading, `decoding="async"`, and potentially conditional rendering of offscreen/far nodes.
- Browser QA should check smooth pan/zoom and console cleanliness.

## Cards masonry requirements

- Keep masonry layout; do not replace it with a plain equal-row grid.
- Make masonry adaptive by viewport width.
- Preserve template-marketplace density and visual browsing feel.
- Keep action affordances available on cards: copy prompt, favorite, edit/open.
- Current Cards mode is visually acceptable and should not be destabilized while working on Explore.

## Copy prompt / language preference requirements

Current bug:

- Card Copy prompt currently copies `prompt_snippet || title`, not the full prompt.

Desired behavior:

- Config should let the user choose preferred prompt language:
  - Traditional Chinese: `zh-Hant`
  - Simplified Chinese: `zh-Hans`
  - English: `en`
- Copy prompt should resolve prompt text in this order:
  1. Preferred language prompt.
  2. English prompt.
  3. Any available full prompt.
  4. Title only as final fallback.
- Card and Detail modal should share the same prompt resolver so behavior is consistent.
- The resolver should work with normalized Traditional Chinese prompts generated during import/create/update.

Implementation options to inspect:

- Add prompt data or a precomputed preferred prompt field to item summaries returned by `/api/items`.
- Keep full prompts on item detail endpoint for modal.
- Add frontend config state/API for preferred language.
- Ensure copy action uses Clipboard API and provides visible success/failure feedback if practical.

## Next implementation plan

Implement in two commits/batches rather than one large mixed change.

### Batch 1 — functional correctness: copy prompt language preference

Goal: fix Copy prompt before deeper visual work.

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

### Batch 2 — Explore orbit UX/performance

Goal: make Explore feel like an ordered orbit map, not a cluttered scatter plot.

Tasks:

1. Refactor orbit layout into deterministic cluster-local geometry:
   - cluster center
   - label exclusion zone
   - ring/lane placement
   - stable angular ordering
2. Add focus mode:
   - click cluster to focus inside Explore
   - focused cluster expands to occupy most of viewport
   - non-focused clusters fade/hide
   - add Back to map / Reset focus control
   - add Open as Cards CTA
3. Add adaptive image level-of-detail:
   - far: dots/small thumbs/collage badges
   - mid: thumbs
   - near/focused: previews
   - modal only: original
4. Tune node caps:
   - global default around `12`
   - focused cluster initially `24`, maybe tune up after performance check
5. Add/update tests/static guards:
   - focus mode exists
   - Open as Cards CTA exists
   - image resolver avoids original path in map where possible
   - LOD-related code/classes exist
6. Verify:
   - `.venv/bin/python -m pytest -q`
   - `npm run build`
   - browser visual QA for global Explore, focused cluster, Cards, and console errors.
7. Run independent Codex Spark review before committing.
8. Commit as a standalone Explore UX/performance improvement.

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
