# Image Prompt Library Project Status

Last updated: 2026-04-26

## Current direction

The app has two distinct browsing modes:

1. **Explore mode = thumbnail constellation graph**
   - Similar to an Obsidian graph-view mental model, but with visual cards: cluster cards are hub nodes and image thumbnails are connected item nodes.
   - Keep real **cluster cards** and real **image thumbnails**; do not degrade the main Explore experience into abstract dots.
   - Global Explore shows multiple cluster-card constellations with a configurable overall thumbnail budget, not a fixed per-cluster thumbnail count.
   - Focus Explore centers the selected cluster card and lays image thumbnails into a stable compact constellation.
   - Current focus direction is accepted by Edward and should be treated as locked unless he explicitly asks for a change.

2. **Cards mode = masonry/template marketplace browsing**
   - Keep the masonry/Pinterest/Vista-style feature.
   - Make the layout adaptive by viewport width so desktop can show more columns without losing masonry density.
   - Preserve first-class actions: **Copy prompt**, **Favorite**, and **Edit**.

## Confirmed product decisions

- No hero section. The top search bar is enough.
- Keep the top toolbar search, logo area, filters entry, config entry, active filter/status strip, Explore/Cards toggle, and floating Add button.
- No `⌘K` / `Ctrl+K` search shortcut for now.
- Detail modal should become the primary lightweight editing surface: title, collection, metadata, prompt blocks, tags, and notes can be edited in place with subtle hover affordance and explicit confirm/cancel controls.
- Detail modal action row should live inside the right-hand detail column above the collection/title: Heart/Favorite and Pencil/Edit aligned left, Close aligned right, all icon-only with polished hover/focus states.
- Prompt block layout order should be English → Traditional Chinese → Simplified Chinese. This is only the editing/display order; copy/display preferred language still follows the user's prompt language setting.
- Detail prompt UI should be a single tabbed prompt panel (`ENG → 繁中 → 簡中`), not three expanded prompt blocks. Prompt copy/edit controls act on the active tab, with long prompts scrolling inside the panel.
- Tags remain at the bottom. Desktop shows each tag's floating top-right unlink `×` on hover; touch/mobile shows unlink controls persistently. A final `+` chip adds tags with smart suggestions.
- Empty notes should show only a faint `Add note` affordance so notes do not consume space when unused.
- Public import positioning: use `wuyoscar/gpt_image_2_skill` as the public example source with CC BY 4.0 attribution, keep OpenNana as an optional local-export adapter, and do not bundle third-party gallery data/media.
- Private one-click generation preview remains private/feature-gated and should not be mentioned in the public README for now.
- Release/license positioning: open-source core under AGPL-3.0-or-later, with commercial licenses available for organizations that need terms outside the AGPL.
- Cards mode masonry is visually acceptable; avoid destabilizing it while working on Explore.
- Explore focus view is now liked by Edward; only minor tuning should be considered later.
- Runtime data/media/database files must not be committed:
  - `library/db.sqlite`
  - `library/db.sqlite-*`
  - `library/originals/`
  - `library/thumbs/`
  - `library/previews/`
- Development port convention:
  - Backend API: `127.0.0.1:8000`
  - Vite frontend: `127.0.0.1:5177`
  - Do **not** use `8787`; it is reserved for Hermes WebUI.

## Current implementation checkpoints

Committed checkpoints:

- `16fe431 Polish toolbar and modal planning checkpoint`
- `214fe6a Implement orbit explore and masonry cards`
- `732d52f Fix prompt copy language preference`
- `3c1fcc1 Avoid Hermes WebUI port for app dev server`
- `a95b7ad Fix copy prompt on LAN HTTP`
- `8f46c69 Polish explore orbit focus mode`
- `0e64939 Plan explore thumbnail constellation graph`
- `520a2da Implement explore thumbnail constellation graph`
- `8602654 Add static repulsion to explore constellation`
- `77bb0c0 Tune explore constellation overlap handling`
- `9686d8d Polish filters modal images and copy feedback`

Current state after `9686d8d` plus the current collection/toast polish pass:

- Explore has been rebuilt as a thumbnail constellation graph.
- Global Explore:
  - Uses cluster cards plus real thumbnail cards.
  - Uses a configurable overall thumbnail budget.
  - Has a final deterministic overlap resolver for global thumbnails and cluster hubs.
  - Browser QA measured `0` overlaps for the current 100-thumbnail global view / 114 total elements.
- Focus Explore:
  - Click/tap a cluster to focus inside Explore.
  - Shows only the focused cluster hub while focused; inactive cluster cards are hidden.
  - Uses deterministic compact slot placement around the focused hub.
  - Uses zero thumbnail rotation for reliable bounding-box packing.
  - Browser QA measured `0` overlaps for the current `人物肖像` focus view: 84 thumbnails / 85 total elements.
  - Edward said the focus view is good and he likes it.
- Cards mode remains masonry/template-marketplace style.
- Prompt copy language preference and LAN HTTP clipboard fallback are implemented.
- Detail modal copy uses the selected prompt-language tab first, then fallback resolver.
- Detail modal now supports lightweight inline editing for title, collection, generated-from/model metadata, author, a single tabbed prompt panel, notes, and tags.
- Detail modal action row is inside the right-hand detail column: Heart/Favorite and Pencil/Edit on the left, Close on the right, aligned above the collection/title.
- Detail prompt tabs are `ENG → 繁中 → 簡中`; long prompts scroll inside the prompt panel, and copy/edit controls operate on the active tab.
- Tag unlink controls are floating mini buttons at the top-right of each tag chip on desktop hover/focus, with persistent touch/mobile visibility.
- Add/Edit now uses prompt order English → Traditional Chinese → Simplified Chinese and includes generated-from/model, author, source URL, and notes fields.
- README now positions OpenNana as an optional local-export adapter and uses `wuyoscar/gpt_image_2_skill` as the public CC BY 4.0 sample screenshot/demo dataset candidate instead of bundling real OpenNana data; screenshots/demo GIFs should preserve attribution and keep imported demo libraries out of git.
- Direction changed for `wuyoscar/gpt_image_2_skill` sample data: public `import-gpt-image-2-skill*.sh` scripts have been removed and live upstream importing is replaced by a curated optional sample bundle. Current bundle metadata has 162 image records, 10 Image Prompt Library collections with localized English/Simplified/Traditional collection names, original English prompts retained, Chinese prompt fields only when source Chinese text exists, and source/license attribution preserved. Distribution remains metadata in git plus image bundle as a GitHub Release asset with `scripts/install-sample-data.sh <en|zh_hans|zh_hant>`; direct-in-repo images remain acceptable only with documented sparse checkout/partial clone guidance.
- Explore blank-space drag/pan is restored for the viewport/canvas/SVG link layer while card/button taps remain protected by tap-vs-drag handling.
- Explore filter selection now auto-fits the focused constellation content to the viewport instead of leaving the previous global pan/zoom transform active.
- Explore unfilter now keeps the focused constellation visible while the all-items refresh completes, then hard-cuts to the final global fit with only a short opacity fade-out/fade-in; global cluster cards should not visibly shrink or settle after appearing.
- Detail modal title inline-editing uses a title-specific reduced font scale so the editable title remains prominent without inheriting the oversized full `h2` desktop scale.
- Detail modal prompt tabs remain visible and clickable in the standard English / Traditional Chinese / Simplified Chinese order. Opening an item selects the preferred prompt language when it has content, otherwise falls back to English/first available content; empty-language tabs stay available for adding a new prompt, show a placeholder/edit affordance when selected, and remain selected after saving new content.

## GitHub AGPL local-install MVP roadmap

Goal: make the project useful for other people to clone from GitHub and run on their own device as a local-first prompt/image reference manager, not just as Edward's local working copy. This is an AGPL-3.0-or-later open-source release target for the core app, with commercial licenses available for organizations that need terms outside the AGPL.

Current assessment:

- Product/local-use MVP: roughly 75–80% there.
- Public AGPL GitHub self-host/local-install MVP: roughly 55–65% there.
- The main remaining gap is not more visual polish; it is installability, first-run behavior, data safety, docs, and release hygiene.

### GitHub MVP checklist

1. **Public README pass** — initial public MVP pass implemented
   - README now uses generic clone/setup/start instructions instead of Edward-specific absolute paths.
   - It explains the local-first/private model, requirements, quick start, development mode, configuration, data layout, adding prompts, optional import adapters, backup, verification, privacy, troubleshooting, and status.
   - Screenshots or short demo GIFs are still pending before a polished public release.

2. **Fresh clone / first-run experience** — current QA pass implemented
   - Clean-checkout setup was tested from a temp copy with an empty external library path.
   - Python requirement is now explicit: Python 3.10+ is required because the backend uses Python 3.10 runtime syntax (`X | None`). `scripts/setup.sh` fails fast with a clear version error instead of creating a broken venv under macOS system Python 3.9.
   - DB migrations initialize automatically for an empty library, and single-service smoke passes on a non-`8787` QA port.
   - Empty Explore/Cards states now have localized empty-state copy plus an inline **Add your first prompt** CTA, in addition to the floating Add button.
   - Browser QA covered manual first prompt add, image upload, edit, detail open, copy prompt, and delete/archive from a fresh empty library.

3. **Install and run scripts** — current public MVP pass implemented
   - Added/improved setup/start/dev/smoke helper scripts: `scripts/setup.sh`, `scripts/start.sh`, `scripts/dev.sh`, and `scripts/smoke-test.sh`.
   - Keep dev ports documented (`8000` backend, `5177` frontend) while avoiding `8787` because it is reserved for Hermes WebUI on Edward's machine.
   - FastAPI can serve the built frontend from `frontend/dist`, so normal local use can run as one backend service after `npm run build`.
   - Shell-provided one-shot overrides (`BACKEND_PORT`, `BACKEND_HOST`, `FRONTEND_PORT`, `IMAGE_PROMPT_LIBRARY_PATH`, `BACKUP_DIR`) now take precedence over `.env`, so documented commands like `BACKEND_PORT=8023 IMAGE_PROMPT_LIBRARY_PATH=/tmp/library ./scripts/start.sh` work reliably.
   - Platform note: macOS/Linux are the primary native script targets; Windows is feasible through WSL 2 today, while native PowerShell/CMD scripts or Docker Compose remain future packaging work.

4. **Configuration story** — initial public MVP pass implemented
   - Added `.env.example` for library path, backend host/port, frontend dev port, and backup directory.
   - Keep repo-local `library/` as the simplest default, but document how users can move data to a durable location such as `~/ImagePromptLibrary/` later.
   - Make clear which files are user data and must be backed up.

5. **Backup / restore story** — current public MVP pass implemented
   - Added `scripts/backup.sh` to archive `library/db.sqlite`, `library/originals/`, `library/thumbs/`, and `library/previews/` into a timestamped backup file.
   - Document restore instructions and local-first privacy/security expectations.
   - Reconfirm `.gitignore` excludes runtime DB/media artifacts and SQLite sidecar files.
   - Fresh-library QA confirmed `IMAGE_PROMPT_LIBRARY_PATH=... BACKUP_DIR=... ./scripts/backup.sh` writes a timestamped `.tar.gz` backup for the selected library path.

6. **Correctness hardening before public MVP**
   - Image-role hardening follow-ups are now implemented: role-aware result-image checks, result-image hero preference, DB-level role validation, cluster preview primary-image de-dupe, and new-item upload-failure cleanup/rollback.
   - Keep `/media` locked down so DB/config/internal files cannot be served.
   - Verify OpenNana import idempotency and fresh manual add/edit/delete/copy/search flows.

7. **Public repo hygiene** — initial public MVP pass implemented
   - `LICENSE` now uses AGPL-3.0-or-later for the core application code, with a commercial license option for organizations that need terms outside the AGPL.
   - Added `CONTRIBUTING.md` and `ROADMAP.md`; concise issue/bug-report guidance lives in `CONTRIBUTING.md`.
   - Decide whether to include sample/demo data or only screenshots; do not commit Edward's runtime `library/` data.
   - Tag a first public alpha release, e.g. `v0.1.0-alpha`, only after fresh-install smoke tests pass.

## Recently implemented: behavior polish for loading, drag, and modal motion

Plan and verification notes: `docs/plans/2026-04-26-behavior-polish-loading-drag-animation.md`.

Implemented on 2026-04-26:

1. **Constellation hold-drag behavior**
   - Click/tap on a thumbnail still opens the detail modal.
   - Pointer movement beyond the tap threshold from a thumbnail or cluster card now enters a pan gesture rather than activating the item/cluster.
   - Constellation thumbnail images use `draggable={false}` and CSS disables native image drag/selection.
   - The gesture path keeps a `useRef` copy of the active pointer state so fast pointer moves do not read stale React state; card/thumb elements also handle pointer move/up/cancel.

2. **Modal opening motion**
   - Added lightweight backdrop fade plus modal opacity/translate/scale entrance.
   - Added a `prefers-reduced-motion` guard.
   - No larger detail skeleton/shell refactor was added in this batch.

3. **Explore filter apply/remove smoothness**
   - `useItemsQuery` now distinguishes `initialLoading` from background `refreshing`.
   - Existing Explore content stays visible during filter refresh, with a subtle refresh indicator instead of the large `.loading` card.
   - Explore focus/clear changes use a short canvas transform transition.

4. **Cards filter apply/remove smoothness**
   - Cards also keep stale content visible during refresh and show only subtle busy feedback.
   - The accepted masonry layout is preserved.

5. **Sparse Cards collection layout**
   - Still deferred by Edward.
   - CSS-column masonry was intentionally left unchanged; no small-collection horizontal grid was added.

Verification recorded for this pass:

- Static/frontend regression suite: `53 passed`.
- Frontend build: passed.
- Browser QA confirmed no large `.loading` flash during Explore filter apply/remove and Cards filter apply.
- Browser QA confirmed modal opens with `modal-backdrop-in` / `modal-panel-in` animations; follow-up fix added a stable detail modal shell plus `modal-content-in` so the loaded content no longer pops in after the shell animation.
- Browser QA confirmed constellation thumbnail images report `draggable=false`.

## Outstanding priorities

### P0 / First priority

1. **Filter drawer / slider controls polish** — implemented
   - Filters drawer now uses the `Collections` wording, functional collection search, selected all-references chip, and count pills.
   - Collection selection is view-aware: Explore focuses the selected cluster; Cards filters the card list to the selected collection.
   - The old helper sentence about VistaCreate quick filter chips has been removed from the UI.
   - Config thumbnail budgets are real range sliders with visible values and descriptive ticks instead of only segmented preset buttons.

### P1 / High priority

2. **Behavior polish: loading, drag, and modal motion** — implemented
   - Implemented scope: constellation thumbnail/card hold-drag uses a tap-vs-drag gesture model; native thumbnail image dragging is disabled; modal opening uses a light reduced-motion-safe entrance animation; Explore/Cards filter refreshes keep stale content visible instead of flashing a large loading card; Explore filter apply/remove uses a short focus/overview transition.
   - Deferred from this batch: sparse Cards collections should not switch to a horizontal grid yet; keep current masonry behavior unchanged.
   - Plan and QA notes: `docs/plans/2026-04-26-behavior-polish-loading-drag-animation.md`.

3. **Cards view lazy image/order stability bug** — implemented
   - Repro described by Edward: open the library, switch to Cards view, scroll down; some cards appear/load midway and the perceived card order reloads/shifts.
   - Root cause confirmed by browser QA: DOM order stayed stable, but lazy images without reserved dimensions expanded after decode inside CSS-column masonry, shifting later cards.
   - `ItemCard` now reserves each first-image aspect ratio from stored `width`/`height`, passes image `width`/`height` attributes, and keeps the accepted masonry/template-marketplace feel. Missing-dimension images keep natural-height rendering as a fallback.

4. **Detail modal duplicate/two images** — implemented
   - Detail modal now deduplicates image records by displayed image path before rendering.
   - Thumbnail rail is hidden when only one unique image remains, so a single-image item shows only the hero image.

5. **Copied toast / visible copy feedback** — implemented; cosmetic fit is low priority revisit
   - Card Copy prompt and detail modal Copy prompt both use the same bottom toast behavior for success/failure.
   - The toast is now a bottom-center glass pill with icon, blur, accent state, and subtle slide/fade animation.
   - Edward confirmed this is better, but still not fully matching the desired theme; revisit later as low priority.

### P2 / Medium priority

6. **Drawer close button cosmetics** — implemented
   - Filters drawer and Config now share a smaller rounded `panel-close` treatment with warm surface, subtle border, shadow, and hover state.

7. **Add header logo branding** — implemented
   - Uses Edward's newer transparent image-cards logo as the left-side header mark.
   - Header brand lockup is simple: larger logo on the left, `Image Prompt Library` text on the right.
   - The `.logo` container is fully transparent with no background, border, or shadow.
   - Kept as toolbar branding, not a hero section or large marketing banner.
   - Logo source currently uses Edward's latest attached 578×578 PNG at `frontend/src/assets/header-logo.png`, preserving its transparency; retained source copy is `header-logo-source.png`; runtime media/database artifacts remain excluded.

8. **Polish global Explore viewport and hover preview** — implemented
   - Global Explore now uses an `explore-mode` app shell that fits the viewport and hides whole-page scroll while keeping the constellation canvas inside the screen.
   - Cards mode keeps the normal document flow and masonry page scrolling.
   - Explore thumbnail cards now use the same CSS-only desktop hover/focus preview scale in both global and focused Explore, guarded by `(hover: hover) and (pointer: fine)`, so behavior stays aligned while touch behavior remains safe.
   - The preview is transform-only (`scale(1.42)`) and preserves node coordinates/rotation through a CSS variable; it does not mutate layout, rerun positioning, or add live physics.

9. **Edit modal data-entry improvements** — implemented
   - Add/Edit modal now has separate English, Traditional Chinese, and Simplified Chinese prompt fields; legacy `original` prompts prefill the Traditional Chinese field for older imported items.
   - Collection input offers existing collection suggestions via datalist while still allowing typed new collections; tag input now also offers existing tag suggestions/chips.
   - Detail and edit modals no longer expose a separate `Original` prompt tab/field; legacy `original` content is folded into Traditional Chinese editing when needed.
   - Image upload UI distinguishes mandatory result image from optional reference photo; uploads persist `result_image` vs `reference_image` roles in the DB/API.
   - Existing items expose a guarded Delete reference action; it calls the existing archive/delete API, hides the item from active lists, refreshes collections/items, and keeps archived recovery possible via the existing `archived=true` API filter.

10. **Image role hardening follow-ups** — implemented
   - Frontend existing-result-image checks are role-aware: only images with `role === 'result_image'` satisfy the required result image, so reference-only items still require a result image.
   - Backend summary/detail image ordering and frontend primary-image helpers prefer `result_image` for cards, detail hero, and Explore thumbnails.
   - Cluster preview images now pick one primary image per active item and prefer the result image over reference images.
   - Added DB-level SQLite role validation via migration `003_image_role_check.sql` with `CHECK(role IN ('result_image', 'reference_image'))`.
   - New item creation rolls back by archiving the just-created item if result/reference image upload fails before save completes.

11. **Full interface language setting** — implemented for main chrome and editor long-tail
   - Added a UI language setting for Traditional Chinese, Simplified Chinese, and English in Config.
   - The setting is stored separately from prompt-copy language preference and localizes main navigation/actions/settings/empty-state labels without changing prompt content.
   - Add/Edit editor long-tail labels, placeholders, required-result/reference-image copy, save/delete/cancel actions, and validation fallback now use the same UI language translator.
   - Traditional Chinese UI copy now uses formal written wording rather than Hong Kong colloquial phrasing.
   - Browser QA verified live switching between Traditional Chinese, English, and Simplified Chinese with no console errors.

12. **Empty collection cleanup** — implemented
   - Collections with zero active items are hidden from `/api/clusters`, so archived/deleted items no longer leave empty collections visible in the sidebar/Explore metadata.
   - Editing the last item out of a collection removes now-unreferenced collection rows, so old collections do not remain after moving the item to another collection.
   - Listing clusters also cleans up pre-existing archived-only collection rows, clearing archived item references first so older empty collections disappear after an upgrade/restart.

### P3 / Low priority

13. **Copied toast theme revisit**
   - Current toast is better but still not fully matching the desired theme; revisit later as low priority.

14. **Minor Explore fine tuning**
   - Possible later tweaks only.
   - Lowest priority because focus view is currently liked and global overlap is solved.

15. **Detail modal polish beyond editor improvements**
   - Existing modal polish is better but can continue to improve.
   - Inspect prompt readability, image rail, action placement, and spacing after higher-priority browsing/editor work.

16. **Future scoring/ranking system**
   - Current priority order is favorite → rating → image availability → deterministic title order.
   - Future scoring can include source quality, prompt completeness, image quality/representativeness, usage/copy count, and recency.

## Discuss-before-action rule

After logging and QA, pause to discuss the remaining priorities and intended approach before implementing the next feature/bugfix. For the next batch, Edward has approved the behavior-polish scope in `docs/plans/2026-04-26-behavior-polish-loading-drag-animation.md`; do not include the deferred sparse Cards layout change unless he asks for it later.

## Explore thumbnail constellation requirements

### Core layout

- Explore should use a thumbnail constellation graph metaphor, similar to Obsidian graph view in structure but **not** in visual abstraction.
- Cluster cards are hub nodes with readable name/count/hidden overflow metadata.
- Image/item nodes are real image thumbnails, not dots, and should visually connect or radiate from their owning cluster card.
- Global Explore should show many cluster-card constellations across a large pan/zoom canvas.
- Focus Explore should center the selected cluster card and arrange that cluster's visible thumbnails outward in a stable, collision-aware constellation.
- Avoid messy circular wreath/ring layouts. Thumbnails should feel like they radiate from the cluster card along natural graph-like spokes or compact force-like separation.
- The layout may calculate once on load/focus and then stay static. Continuous physics animation is not required and should be avoided unless explicitly desired later.

### Interaction

- Pan the canvas.
- Wheel/pinch zoom the canvas.
- Reset view.
- Tap/click an image thumbnail to open the detail modal.
- Search/filter should hide or de-emphasize non-matching thumbnails.
- Cluster/item activation should use a tap-vs-drag threshold so slight pointer movement does not make cluster click/focus feel unreliable.
- If a gesture starts on a thumbnail or cluster card and moves beyond the tap threshold, it should become viewport panning rather than native image dragging or item/cluster activation.
- Constellation thumbnail images should disable native browser drag behavior (`draggable={false}` plus CSS/user-select safeguards).

### Cluster click/focus behavior

- Single click cluster = focus that cluster inside Explore, not immediately switch to Cards.
- Focus mode preserves the Explore/galaxy mental model.
- Focused cluster occupies the map center.
- Other clusters/items hide while focused.
- User can return to global Explore by clearing the active cluster filter/status chip.
- Focus mode includes **Open as Cards** for deep browsing in filtered Cards mode.

### Visible thumbnail budgets / caps

- Global Explore uses an **overall configurable thumbnail budget**, not a fixed per-cluster cap.
- Default global thumbnail budget is currently `100` total thumbnails across all clusters.
- Focus Explore uses a **configurable focus thumbnail budget**.
- Focus budget supports `100` and is currently readable with the accepted compact layout.
- Budget settings are exposed in Config as slider controls:
  - `Global thumbnails`: range `50` to `150`, default target `100`.
  - `Focus thumbnails`: range `24` to `100`, default target `100`.

### Node prioritization

Current priority order:

1. Favorite items first.
2. User rating.
3. Items with usable thumbnails/previews.
4. Stable deterministic title ordering.

## Copy prompt / language preference behavior

Status: implemented and committed.

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
- Copy prompt uses a shared clipboard helper with textarea/`execCommand('copy')` fallback for LAN HTTP origins where `navigator.clipboard` is unavailable.
- Visible feedback is now shared: card copy and detail modal copy both use the same modern bottom toast.

## Latest QA / review notes

Logged on 2026-04-26 for behavior-polish planning:

- Edward accepted the proposed fixes for constellation thumbnail/card hold-drag panning, light modal entrance animation option A, Explore filter refresh smoothness, and Cards filter refresh smoothness.
- Edward explicitly deferred the sparse Cards collection layout change; keep CSS-column masonry unchanged in the next batch even though small collections can currently appear top-to-bottom rather than left-to-right.
- Inspection root causes: `useItemsQuery()` sets `loading=true` for every query change, `App` inserts a large `.loading` block during filter refresh, constellation thumbnail images still have native `draggable=true`, thumbnail/cluster pointer handlers stop propagation before viewport pan can take over, and detail modal opening currently swaps from immediate loading state to content without an intentional entrance animation.
- Next plan saved at `docs/plans/2026-04-26-behavior-polish-loading-drag-animation.md`.

Logged on 2026-04-26 for detail-editing/import-positioning planning:

- Edward confirmed inline detail editing direction: subtle hover affordances, explicit confirm/cancel controls, icon-only Heart and Pencil header actions, copy icon in each prompt block, tag unlink on hover for desktop and persistent unlink controls for touch/mobile, and faint `Add note` when notes are empty.
- Add/Edit form should keep the structured create/advanced edit role, but add/surface Image generated from/model, Author defaulting to `User`, optional Source URL, and Notes; prompt field order should become English, Traditional Chinese, Simplified Chinese.
- Prompt copy/display language preference remains independent from edit/display order and should continue to follow the user setting.
- Public import example should shift from OpenNana to `wuyoscar/gpt_image_2_skill` where practical because it is a public CC BY 4.0 prompt gallery; OpenNana remains an optional local-export adapter with no bundled data/media.
- Private one-click generation preview remains intentionally private and should not be documented in the public README for now.

Logged on 2026-04-26 for the fresh clone / empty-library first-run pass:

- Fresh setup surfaced a public-blocking Python mismatch: macOS system `python3` was Python 3.9.6, while backend code already uses Python 3.10 `X | None` syntax. The project now documents and enforces Python 3.10+; `scripts/setup.sh` rejects older Python with a clear error and supports `PYTHON=/path/to/python3.10 ./scripts/setup.sh`.
- Fresh script QA surfaced `.env` precedence drift: `.env` defaults could override shell one-shot env vars. `scripts/start.sh`, `scripts/dev.sh`, and `scripts/backup.sh` now preserve incoming shell env values over `.env` defaults for documented local-install overrides.
- Empty-library browser QA now shows a clearer inline first-run CTA: `Your library is empty` plus `Add your first prompt` in both Explore/Cards empty states.
- Manual fresh-library QA covered adding a first prompt with a result image, editing the title, opening the detail modal, copying the Traditional Chinese prompt text, and deleting/archiving the item. Console QA showed no JavaScript errors.
- Delete/archive QA found and fixed stale metadata: archived items no longer contribute cluster preview images or active tag counts, preventing empty libraries from showing leftover thumbnail/tag metadata after deletion.
- Fresh backup QA confirmed `scripts/backup.sh` works with explicit `IMAGE_PROMPT_LIBRARY_PATH` and `BACKUP_DIR`, writing a timestamped `.tar.gz` containing the selected library DB/media paths.

Logged on 2026-04-25 for the collection drawer / shared-toast pass:

- Edward confirmed the filter drawer and collection selection behavior are okay.
- Edward said the shared toast is better but still does not fully fit the expected theme; keep it as a low-priority revisit, not the next focus.
- Edward flagged cosmetic ugliness in the Filters drawer and Config close buttons.
- Edward reported a possible Cards view bug: after opening the library, switching to Cards, and scrolling down, some cards appear/load midway and the card order seems to reload. Treat this as the next likely bug investigation, with a current hypothesis around image-load reflow in CSS masonry.
- Cards global-view inspection confirmed the likely root cause: DOM order stayed stable across scroll/load, but unloaded lazy images started with fallback/min heights and expanded after decode, which shifted later cards in the CSS-column masonry. Example: `粉色少女风珍珠奶茶特写广告` changed from card height `244` to `322` after image decode (`natural 336x420`); subsequent cards shifted down by the accumulated height delta while DOM order remained stable. API item summaries already include original image `width`/`height`, but `ItemCard` did not pass width/height attributes or reserve an aspect-ratio wrapper.
- Cards stability fix implemented: `ItemCard` now wraps images in a `card-image-frame`, reserves aspect ratio from `first_image.width`/`height`, and passes `width`/`height` attributes while preserving CSS-column masonry. Images without stored dimensions fall back to natural image height instead of being forced into a cropped 4:3 box.
- Post-fix browser QA on global Cards view showed `251` cards, `251` aspect-ratio frames, `251` reserved-ratio frames, `0` natural fallback frames for the current complete dataset, `0` images missing dimension attributes, stable first-40 DOM order, and no sampled card top/height changes after scroll/decode (`changed: []`).
- Independent Codex Spark read-only review found no critical TypeScript/CSS regressions. Its main medium concern was missing-dimension image cropping; the implementation now keeps missing-dimension images on natural-height fallback instead of forcing a 4:3 crop.
- Filters and Config close buttons now use the shared `panel-close` style; browser DOM QA confirmed two visible 38×38 rounded buttons for `Close filters` and `Close config`.
- Test/build verification passed after the Cards/close-button fix: `.venv/bin/python -m pytest -q` reported `29 passed`; `npm run build` passed; `git diff --check` passed.
- New roadmap notes from Edward: Add header logo branding was completed as the first implementation target, followed by polishing the Global Explore viewport and hover preview; toast theme should be revisited later only; editor improvements should add separate Traditional/Simplified/English prompt editing, smart existing-cluster suggestions while typing Collection, mandatory result image upload plus optional reference photo upload; full interface UI language setting should support Traditional Chinese, Simplified Chinese, and English separately from prompt-copy language.
- Header logo implemented and revised: `TopBar` now uses Edward's newer transparent image-cards logo on the left and `Image Prompt Library` text on the right; after trying a cropped/optimized derivative and then the larger original, Edward asked to swap again, so `frontend/src/assets/header-logo.png` now preserves the latest attached 578×578 transparent PNG, displayed at 64×64. The retained source attachment is named `header-logo-source.png`.
- Header logo QA: static regression covers the imported latest attached logo asset, RGBA transparency, 578×578 dimensions, `.logo-mark` image, single-line `Image Prompt Library` text, removal of the old Sparkles placeholder/subtitle, transparent `.logo` container (`background: transparent`, `border: 0`, `box-shadow: none`, `padding: 0`), and 64×64 logo sizing; browser DOM QA confirmed the latest image natural size, transparent container styles, and 64×64 image dimensions.
- Global Explore viewport/preview implemented: Explore mode now uses a viewport-fit app shell with whole-page scrolling hidden while the constellation remains in-screen; Cards mode remains document-scrollable for masonry browsing. Desktop hover/focus preview uses CSS-only transform scaling (`scale(1.42)`) under `(hover: hover) and (pointer: fine)` in both global and focused Explore, keeps touch behavior safe, preserves node coordinates/rotation via `--node-rotation`, and does not mutate layout or rerun constellation positioning.
- Browser QA confirmed Explore global view `documentElement.scrollHeight == innerHeight` and `body.scrollHeight == innerHeight` at the tested viewport, `.app` was `explore-mode` with `overflow: hidden`, and Cards mode switched back to normal scroll with `252` cards and a much taller document height. Browser vision confirmed the Explore canvas fits in the viewport and the constellation layout remains intact.
- Browser QA confirmed the filter drawer title is `Collections`, the previous helper sentence is absent, and collection search filters the list, e.g. `科技` only shows `科技科幻`.
- Browser QA confirmed Explore-mode collection selection focuses the selected cluster: `科技科幻` produced a focus panel with `14 references · 14 visible` and kept Explore active.
- Browser QA confirmed Cards-mode collection selection filters cards: selecting `人物肖像` showed `84 references` and 84 cards while Cards stayed active.
- Browser QA confirmed card Copy prompt and detail modal Copy prompt both show the shared `Prompt copied` bottom toast with `toast copy-toast elegant-toast success`; detail modal copy button text stays stable as `Copy prompt`.
- Browser QA reconfirmed detail modal image dedupe: modal duplicate image sources were `[]`.
- Browser console had no JS errors.

Logged on 2026-04-25 before and after the filter/modal/copy pass:

- Browser QA confirmed Global Explore still reports `0` DOM overlaps for current global thumbnails and cluster cards.
- Pre-fix QA confirmed Copy prompt had no toast/visible feedback after clicking Copy; post-fix QA confirmed card copy shows `Copied prompt` toast and detail copy changes button state to `Copied prompt`.
- Pre-fix QA confirmed the detail modal could render duplicate image entries: one hero preview plus two identical thumbnail rail images for the same item/image source; post-fix QA confirmed the repro item now renders one hero image and `duplicateSrcs: []`.
- Browser visual QA confirmed the new filter drawer is VistaCreate-like: sliding left drawer, search-like control, selected all-references chip, and count-pill filter chips.
- Browser visual QA confirmed Config now uses polished range sliders with visible numeric values and tick labels for global/focus thumbnail budgets.
- Codex Spark read-only review agreed the priorities are sensible.
- Codex Spark identified the duplicate-image cause: `ItemDetailModal.tsx` rendered `primaryImage` in the hero and then mapped `item.images` into the thumbnail rail without deduplicating the displayed image source.
- Codex Spark noted a future guardrail for Explore: focused compact slots have a fallback that could reuse the last slot if slots are exhausted; add a regression if budget/canvas sizing changes later.

## Verification checklist for future UI passes

- `.venv/bin/python -m pytest -q`
- `npm run build`
- Browser console has no JS errors.
- Explore global map loads and is readable.
- Explore focused cluster mode works and can return to global map.
- DOM overlap script reports no overlaps for current target views, if touching Explore layout.
- Cards masonry still looks correct.
- Detail modal opens from both Explore and Cards.
- Copy prompt uses preferred language and full prompt, not snippet/title.
- Favorite and Edit still work.
- No runtime media/database artifacts are committed.
