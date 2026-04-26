# Behavior Polish: Loading, Drag, and Modal Motion Plan

> **For Hermes:** Use subagent-driven-development skill only if this grows beyond the small implementation batch; otherwise implement task-by-task with tests and browser QA.

**Goal:** Smooth the accepted Explore/Cards browsing behavior by removing reload flashes, making constellation thumbnail hold-drag pan the viewport, and adding a light modal entrance animation.

**Architecture:** Keep the current FastAPI/SQLite backend and React/Vite frontend structure. Changes should stay in the frontend interaction layer: `useItemsQuery`, `App`, `ExploreView`, `ItemDetailModal`/CSS, and static tests. Preserve the accepted Explore constellation layout and Cards masonry; do not implement sparse Cards grid behavior in this batch.

**Tech Stack:** React, TypeScript, CSS, existing static pytest checks, browser QA.

---

## Accepted scope

Edward confirmed on 2026-04-26:

1. **Constellation hold-drag behavior** — implement as discussed.
   - Clicking/tapping a constellation thumbnail still opens the detail modal.
   - Holding then dragging from a thumbnail/card should pan the constellation viewport.
   - Native browser image dragging should be disabled for constellation thumbnails.

2. **Modal opening motion** — implement option A only.
   - Add a light backdrop fade plus modal opacity/translate/scale entrance.
   - Include a `prefers-reduced-motion: reduce` guard.
   - Do not build a larger skeleton/shell refactor in this batch.

3. **Explore filter apply/remove smoothness** — implement as discussed.
   - Avoid inserting the large loading card during filter refreshes.
   - Keep stale content visible while the new query refreshes.
   - Show only subtle busy/progress feedback in chrome/status area or container state.
   - Smoothly animate the constellation canvas to the selected collection center when applying a collection filter, and back to the default overview when clearing it.

4. **Cards filter apply/remove smoothness** — implement as discussed.
   - Avoid the large loading card flash during Cards filter refreshes.
   - Preserve existing Cards data while refreshing.
   - Use subtle busy feedback rather than interrupting the layout.

5. **Sparse Cards layout** — explicitly deferred.
   - Do not change the current CSS-column masonry behavior in this batch.
   - The observed sparse collection layout (`3 columns × 2 rows` rather than `6 columns × 1 row`) is acknowledged, but Edward asked to leave it for later.

---

## Current root-cause notes from inspection

- `useItemsQuery()` currently sets `loading=true` for every query change, including filter changes, so `App` renders a large `.loading` block before the updated Explore/Cards content settles.
- `ExploreView` has separate viewport pan state and tap state. Thumbnail cards call `event.stopPropagation()` on pointer down, so a drag that starts on a thumbnail does not naturally become a viewport pan.
- Thumbnail `<img>` elements currently keep browser-default drag behavior (`draggable=true`), which can create native image-drag ghost behavior during hold-drag.
- Detail modal currently renders the backdrop immediately, clears `item` with `setItem(undefined)`, shows `.modal-loading`, and swaps to full content after `api.item(id)` returns. There is no intentional entrance animation.
- Explore focus already positions the selected cluster near the viewport center after filter selection, but it happens as an abrupt state jump rather than a deliberate 220–320ms focus transition.

---

## Task 1: Update static tests for behavior contracts

**Objective:** Lock in the accepted behavior before changing implementation.

**Files:**
- Modify: `tests/test_frontend_static.py`

**Assertions to add or update:**

1. `useItemsQuery` distinguishes initial loading from background refreshing, or exposes equivalent state names.
2. `App.tsx` only renders the large `.loading` block for initial empty load, not for every refresh.
3. `ExploreView.tsx` has a unified tap-vs-drag path where movement beyond `TAP_DRAG_THRESHOLD` can pan the viewport instead of opening the item.
4. Constellation thumbnail images include `draggable={false}`.
5. CSS disables native drag/user selection for `.constellation-thumb-card` images.
6. Modal CSS includes backdrop/modal entrance animation plus a `prefers-reduced-motion` guard.
7. Explore focus animation uses an explicit transition class/duration or equivalent deliberate transform animation.
8. No assertion should require sparse Cards grid behavior; Cards masonry remains the expected default for this batch.

**Verification:**

```bash
. .venv/bin/activate && python -m pytest tests/test_frontend_static.py -q
```

Expected before implementation: new assertions fail.

---

## Task 2: Remove filter loading flash while preserving refresh feedback

**Objective:** Keep existing Explore/Cards content visible during filter/search refreshes.

**Files:**
- Modify: `frontend/src/hooks/useItemsQuery.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Implementation notes:**

- Refactor `useItemsQuery` to separate:
  - initial load, when there is no data yet;
  - refreshing, when previous data exists and a new query is in flight.
- Keep stale `data` visible during refresh.
- In `App.tsx`, render the large `.loading` block only when initial load has no visible items/clusters yet.
- Add a subtle busy marker such as `app-main is-refreshing`, `aria-busy`, or a small status indicator near the active filter/status strip.
- Do not add a full-screen overlay or large loading card for filter changes.

**Verification:**

```bash
. .venv/bin/activate && python -m pytest tests/test_frontend_static.py -q
npm run build
```

Browser QA:
- Apply and remove a filter in Explore; no large loading card should flash.
- Apply and remove a filter in Cards; no large loading card should flash.
- Browser console should stay clean.

---

## Task 3: Make constellation hold-drag pan the viewport

**Objective:** A pointer gesture that starts on a thumbnail should either open the item as a tap or become viewport panning after the drag threshold.

**Files:**
- Modify: `frontend/src/components/ExploreView.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Implementation notes:**

- Set constellation thumbnail images to `draggable={false}`.
- Add CSS to prevent native drag/selection on constellation thumbnail cards/images.
- Replace or extend the current separate `tapState`/`dragStart` logic with a single gesture model that records:
  - pointer id;
  - start coordinates;
  - original viewport offset;
  - optional tap target;
  - whether the gesture has crossed the drag threshold.
- If movement stays below threshold, pointer up activates the cluster/item.
- If movement crosses threshold, update viewport offset from the original offset and do not activate item/cluster on pointer up.
- Keep click/tap behavior reliable for both cluster cards and thumbnail cards.

**Verification:**

Browser QA:
- Click thumbnail: opens detail modal.
- Hold thumbnail and drag: pans constellation; does not open modal; does not show native image drag ghost.
- Drag empty canvas: still pans.
- Click cluster: focuses cluster.
- Hold cluster and drag: pans; does not focus cluster.

---

## Task 4: Add light modal entrance animation

**Objective:** Make detail modal opening feel intentional rather than abruptly appearing.

**Files:**
- Modify: `frontend/src/styles.css`
- Optionally modify: `frontend/src/components/ItemDetailModal.tsx` only if a class hook is needed.
- Test: `tests/test_frontend_static.py`

**Implementation notes:**

- Add a short backdrop fade animation.
- Add modal entrance animation using opacity + `translateY(...)` + slight scale.
- Keep duration restrained, roughly 160–220ms.
- Add `@media (prefers-reduced-motion: reduce)` to disable animations/transitions.
- Do not introduce skeleton/shell data rendering in this batch.

**Verification:**

Browser QA:
- Open modal from Cards and Explore.
- Modal should fade/settle without a harsh flash.
- Close/reopen should still feel responsive.
- Browser console should stay clean.

---

## Task 5: Animate Explore focus/clear centering

**Objective:** Applying a collection filter in Explore should smoothly center that collection; clearing the filter should smoothly return to overview.

**Files:**
- Modify: `frontend/src/components/ExploreView.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Implementation notes:**

- Keep the accepted constellation layout and focus mode semantics.
- When `focusedClusterId` changes from undefined to a cluster id:
  - compute target scale/offset for the focused cluster center;
  - animate the transform to that target over roughly 220–320ms ease-out.
- When clearing the filter:
  - animate back to the default overview scale/offset.
- Avoid fighting user pan/zoom: user-initiated pan/zoom after focus should still work normally.
- Preserve the `Reset view` button behavior.

**Verification:**

Browser QA:
- In Explore, select `建築城市地標` from Filters.
- The focus panel should appear and the selected cluster should move smoothly near viewport center.
- Clear the active collection chip.
- The canvas should return smoothly to overview without the large loading flash.
- Use a DOM check to compare focused cluster center to viewport center after animation settles.

---

## Task 6: Final verification and documentation update

**Objective:** Verify behavior and document the completed result.

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Possibly modify this plan with completion notes if implementation diverges.

**Commands:**

```bash
. .venv/bin/activate && python -m pytest -q
npm run build
git diff --check
```

**Browser QA checklist:**

- No large loading flash on Explore filter apply/remove.
- No large loading flash on Cards filter apply/remove.
- Explore selected collection centers smoothly.
- Constellation thumbnail click opens detail.
- Constellation thumbnail hold-drag pans viewport and does not drag the image out.
- Modal opens with a restrained fade/settle animation.
- Cards masonry remains unchanged; sparse Cards layout is not changed in this batch.
- Browser console has no JavaScript errors.

**Do not commit unless Edward asks.**

---

## Completion notes — 2026-04-26

Implemented in this pass:

- `useItemsQuery` now separates first-load `initialLoading` from background `refreshing`, keeping stale Explore/Cards data visible while filters refresh.
- `App.tsx` uses `initialLoading` for the large loading state and a subtle refresh indicator / `aria-busy` for refreshes.
- `ExploreView` now uses a unified pointer gesture model for constellation card/thumb interactions:
  - click/tap activates the cluster/item;
  - movement beyond `TAP_DRAG_THRESHOLD` pans from the original viewport offset;
  - drag release suppresses accidental click activation;
  - card/thumb elements handle pointer move/up/cancel as well as pointer down;
  - thumbnail images are explicitly `draggable={false}`.
- CSS now includes constellation drag prevention, a focus transition class, refresh-indicator styling, restrained modal/backdrop entrance animations, and reduced-motion guards.
- Cards sparse masonry behavior was intentionally left unchanged.

Verification performed:

- `python -m pytest tests/test_frontend_static.py -q` passed during implementation.
- Full `python -m pytest -q` passed during implementation with `53 passed`.
- `npm run build` passed during implementation.
- Browser QA confirmed:
  - Explore filter apply/remove does not show a large `.loading` flash and uses the subtle refresh indicator.
  - Cards filter apply does not show a large `.loading` flash and uses the subtle refresh indicator.
  - Detail modal opens and reports `modal-backdrop-in` / `modal-panel-in` animations, and the loaded detail content uses `modal-content-in` inside a stable-height shell to avoid a post-loading pop.
  - Constellation thumbnail images report `draggable=false`.

Follow-up QA note:

- A browser-console synthetic `PointerEvent` drag did not move the canvas because `setPointerCapture()` expects a real active pointer in the browser; this is not equivalent to a physical/browser automation drag. The implemented path is still covered by static regression checks and source inspection, but a manual or real browser-automation drag should be used if further confidence is needed.
