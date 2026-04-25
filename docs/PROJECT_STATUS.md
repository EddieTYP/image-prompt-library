# Image Prompt Library Project Status

Last updated: 2026-04-25

## Current direction

The app has two distinct browsing modes:

1. **Explore mode = spatial orbit map**
   - Similar to the previous OpenNana `html-gallery` experience.
   - Cluster labels are visible anchors on a large pan/zoom canvas.
   - Image/item thumbnails orbit around cluster names.
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
- Detail modal and edit modal are much better after the latest polish pass, but can continue to improve.
- Future UI must preserve first-class actions:
  - Copy prompt
  - Favorite
  - Edit

## Explore orbit map requirements

### Core layout

- Replace the temporary cluster-card orbit concept with a full spatial canvas.
- Cluster labels should be rendered as in-canvas anchors with name and count.
- Image/item nodes should be positioned around the relevant cluster label.
- The user should be able to visually understand cluster scale and topic neighborhoods.

### Interaction

- Pan the canvas.
- Wheel/pinch zoom the canvas.
- Reset view.
- Click a cluster label to focus/filter that cluster.
- Click an image node to open the detail modal.
- Search/filter should hide or de-emphasize non-matching nodes.

### Maximum visible nodes per cluster

Showing every item around every cluster is not practical for usability or performance.

Initial proposal:

- Default max visible nodes per cluster: `12`.
- Large/important clusters may show up to `18` or `24` after tuning.
- Tiny clusters can show all items if count is below the cap.
- The cluster label should still show the total cluster count, not only displayed nodes.
- If a cluster has hidden overflow, show a subtle indicator such as `+67 more`.
- Clicking/focusing a cluster can expand that cluster's visible cap or switch to Cards mode filtered to that cluster.

### Node prioritization

Initial priority order:

1. Favorite items first.
2. Later: scored items from a scoring/ranking system.
3. Until scoring exists: representative/diverse fallback using available metadata.
   - Prefer items with usable thumbnails/previews.
   - Avoid showing many near-duplicate images from the same item when other items exist.
   - Mix tags/styles where possible.
   - Stable deterministic ordering so the map does not reshuffle unexpectedly.

### Future scoring system idea

A future item score can combine:

- manual favorite/pin status
- user rating
- source quality
- prompt completeness
- image quality/representativeness
- usage frequency or copy count
- recency, if desired

The orbit map should be designed so the ranking source can be swapped later without redesigning the UI.

## Cards masonry requirements

- Restore/keep masonry layout; do not replace it with a plain equal-row grid.
- Make masonry adaptive by viewport width.
- Target: desktop should use available width better than the previous fixed 5-column feel.
- Preserve template-marketplace density and visual browsing feel.
- Keep action affordances available on cards: copy prompt, favorite, edit/open.

## Next implementation pass proposal

1. Remove the temporary Explore cluster-card collage implementation.
2. Build a deterministic orbit layout function for clusters and representative item nodes.
3. Render Explore as a pan/zoom SVG/HTML canvas with cluster labels and thumbnail nodes.
4. Add cluster node caps and prioritization:
   - favorites first
   - deterministic representative fallback
   - `+N more` overflow indicator
5. Restore Cards view masonry while keeping adaptive column density.
6. Ensure copy prompt, favorite, and edit remain visible requirements in card/modal UI.
7. Add/update static frontend tests to guard against regressions:
   - no hero section
   - no keyboard shortcut requirement
   - Explore is a spatial orbit map, not cluster cards
   - Cards keep masonry/adaptive behavior
   - copy/favorite/edit action strings/classes exist
8. Verify with:
   - `.venv/bin/python -m pytest -q`
   - `npm run build`
   - browser smoke test on Explore, Cards, detail modal, and console errors

## Open questions before implementation

None blocking. Suggested defaults unless Edward changes them:

- Start with `12` visible nodes per cluster.
- Expand focused cluster to `24` visible nodes or switch to filtered Cards view on click.
- Use Favorite-first ordering now, and leave scoring as a later extension.
- Keep pan/zoom/reset in Explore, but defer decorative motion until the static orbit map feels right.
