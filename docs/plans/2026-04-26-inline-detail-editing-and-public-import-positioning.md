# Inline Detail Editing and Public Import Positioning Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the item detail modal into the primary lightweight editing surface, align the Add/Edit form with the same metadata model, and reposition public bulk import examples around a generic format plus `wuyoscar/gpt_image_2_skill` rather than bundled OpenNana data.

**Architecture:** Keep the existing FastAPI/SQLite item model and React modal architecture. Use focused inline edit controls in `ItemDetailModal` for small item changes, while keeping `ItemEditorModal` as the structured create/advanced edit form. Treat importers as source-specific adapters into a canonical item/prompt/image shape.

**Tech Stack:** FastAPI, SQLite, Pydantic, Vite, React, TypeScript, CSS, pytest static/API regression tests.

---

## Product decisions captured on 2026-04-26

- Detail modal becomes the primary lightweight editing surface.
- Add/Edit modal remains for Add flow and advanced structured editing.
- Inline editable fields should have subtle hover affordance.
- Title, Collection, metadata text, prompt blocks, and notes should use confirm/cancel controls for edits.
- Favorite, Edit, and Close actions are icon-only in the detail column action row above the collection/title: Heart/Pencil on the left and Close on the right.
- Prompt copy/edit actions live inside a single tabbed prompt panel whose tabs are English, Traditional Chinese, Simplified Chinese.
- The prompt panel preserves internal scrolling for long prompts; edit confirm/cancel controls sit inside the panel at bottom-right.
- Copy/display preferred language remains controlled by the user's prompt language setting; the above order is only layout/editing order.
- Tags stay at the bottom: each tag can unlink from the current item with a small `×`; desktop shows the `×` on tag hover, while touch/mobile shows it persistently. A final `+` chip adds tags with smart suggestions.
- Empty notes should not consume space: show only a faint `Add note` affordance.
- Public README should not mention the private one-click generation preview for now.
- Use `wuyoscar/gpt_image_2_skill` as the public example source because it is a public GitHub prompt gallery with CC BY 4.0 attribution requirements.
- Keep OpenNana as an optional local-export adapter; do not bundle OpenNana data/media.

---

## Task 1: Add/update static tests for the new modal interaction contract

**Objective:** Lock the planned detail modal controls into static regression tests before implementation.

**Files:**
- Modify: `tests/test_frontend_static.py`
- Inspect: `frontend/src/components/ItemDetailModal.tsx`
- Inspect: `frontend/src/styles.css`

**Steps:**
1. Add static assertions for icon-only modal header actions:
   - heart/favorite button near the left side of the modal header
   - pencil/edit button near the left side of the modal header
   - close button still present and styled via shared icon button class
2. Add static assertions for inline edit affordance classes and controls:
   - title inline edit
   - collection inline edit
   - metadata inline edit
   - prompt inline edit
   - notes inline edit
   - confirm/cancel buttons
3. Add static assertions that prompt blocks include a copy icon button rather than relying only on a large `Copy prompt` action.
4. Add static assertions for tag unlink/add controls:
   - hover-only unlink style for desktop
   - touch/mobile always-visible unlink style
   - add-tag chip/button with suggestions.
5. Run targeted static tests and verify they fail before implementation.

**Verification:**

```bash
. .venv/bin/activate && python -m pytest tests/test_frontend_static.py -q
```

Expected before implementation: failing tests for the new modal contract.

---

## Task 2: Implement reusable inline-edit primitives

**Objective:** Avoid duplicating confirm/cancel/edit-state logic across title, collection, metadata, prompt, and notes.

**Files:**
- Create or modify: `frontend/src/components/InlineEditableField.tsx`
- Create or modify: `frontend/src/components/InlineEditableTextArea.tsx`
- Modify: `frontend/src/styles.css`

**Steps:**
1. Implement a small inline text field component with:
   - read view
   - subtle hover affordance
   - double-click or explicit affordance to enter edit mode
   - confirm/cancel icon buttons
   - Enter confirms, Escape cancels
   - no blur auto-save by default
2. Implement textarea variant for prompt blocks and notes.
3. Use shared CSS classes for:
   - `.inline-editable`
   - `.inline-editable:hover`
   - `.inline-edit-controls`
   - `.inline-edit-confirm`
   - `.inline-edit-cancel`
4. Keep styling lightweight and consistent with existing rounded modal controls.

**Verification:**

```bash
npm run build
. .venv/bin/activate && python -m pytest tests/test_frontend_static.py -q
```

---

## Task 3: Wire detail modal inline editing to existing item update API

**Objective:** Let users edit common fields directly inside the detail modal.

**Files:**
- Modify: `frontend/src/components/ItemDetailModal.tsx`
- Modify: `frontend/src/api.ts` if needed
- Modify: `frontend/src/App.tsx` if refresh callbacks need to be passed through
- Modify: `tests/test_frontend_static.py`

**Fields and behavior:**
- Title: inline edit with confirm/cancel.
- Collection: inline edit with existing collection suggestions and typed new collection support.
- Metadata row:
  - Image generated from / model, shown as the first metadata segment.
  - Author, shown as `@Author`; default for new items should be `User`.
  - Source URL shown as icon-only link after author when present.
- Prompt blocks:
  - Order: English, Traditional Chinese, Simplified Chinese.
  - Read mode has copy icon in the top-right of each prompt block.
  - Edit mode has confirm/cancel controls.
  - Copy text still follows selected/visible prompt behavior and app-level toast feedback.
- Tags:
  - Existing tags render as chips.
  - `×` unlinks tag from this item only.
  - `+` opens an inline add-tag input with suggestions.
- Notes:
  - Existing note renders as a subtle note block.
  - Empty note renders only a faint `Add note` affordance.

**Verification:**

```bash
. .venv/bin/activate && python -m pytest tests/test_frontend_static.py -q
npm run build
```

Browser QA:
- Open detail from Cards and Explore.
- Edit title, collection, model, author, prompt, tags, and notes.
- Confirm/cancel paths work.
- List/detail data refreshes without stale state.
- Console has no JavaScript errors.

---

## Task 4: Align Add/Edit modal with the updated item structure

**Objective:** Keep structured create/advanced edit consistent with the new detail modal metadata and prompt order.

**Files:**
- Modify: `frontend/src/components/ItemEditorModal.tsx`
- Modify: `frontend/src/utils/i18n.ts`
- Modify: `tests/test_frontend_static.py`

**Changes:**
1. Reorder prompt fields:
   - English
   - Traditional Chinese
   - Simplified Chinese
2. Add or surface fields:
   - Image generated from / model — optional, default from existing app model default.
   - Author — default `User` for new items.
   - Source URL — optional.
   - Notes — optional, separate from prompt content.
3. Preserve existing fields:
   - Title
   - Collection with suggestions
   - Tags with suggestions
   - Required result image
   - Optional reference image
4. Keep prompt-copy preferred language setting independent from form ordering.

**Verification:**

```bash
. .venv/bin/activate && python -m pytest tests/test_frontend_static.py -q
npm run build
```

Browser QA:
- Add a new item with default author `User`.
- Add English/Traditional/Simplified prompts in the new order.
- Add source URL and notes.
- Edit same item through the structured editor and through inline detail controls.

---

## Task 5: Update public import documentation and script positioning

**Objective:** Make the public GitHub story explain bulk import without implying OpenNana is the universal or bundled source.

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `scripts/import-opennana.sh`
- Optionally create: `docs/import-format.md`
- Optionally create future plan placeholder: `docs/plans/2026-04-26-gpt-image-skill-import-adapter.md`

**Changes:**
1. Document the current canonical item structure:
   - item metadata
   - prompts
   - images with `result_image` / `reference_image`
   - tags
   - collection
   - source attribution
2. Explain that OpenNana importer is an optional local-export adapter and that this repo does not bundle OpenNana data/media.
3. Replace the hardcoded absolute path in `scripts/import-opennana.sh` with a required `OPENNANA_GALLERY_JSON` or positional path argument.
4. Use `wuyoscar/gpt_image_2_skill` as the public example source because it is a public GitHub prompt gallery with CC BY 4.0 license; state attribution requirements clearly.
5. Do not mention private one-click generation preview in public README.

**Verification:**

```bash
git diff --check
. .venv/bin/activate && python -m pytest -q
npm run build
```

Manual review:
- README contains no Edward-specific absolute paths.
- README does not imply third-party data is bundled.
- README does not mention private generation preview.
- Import script fails with a helpful message if no source path is provided.

---

## Task 6: Final QA and commit

**Objective:** Verify modal UX, import docs, and repo hygiene before committing.

**Files:**
- All modified files

**Steps:**
1. Run full backend/static test suite.
2. Run frontend build.
3. Run `git diff --check`.
4. Browser QA:
   - Cards still load and masonry remains stable.
   - Explore opens detail modal from thumbnail nodes.
   - Detail modal inline edits work.
   - Prompt copy icon works and shows toast.
   - Favorite heart and pencil edit buttons work.
   - Close button hover/focus state is visible.
   - Tags unlink/add works on desktop and mobile/touch responsive mode if feasible.
5. Check git status and ensure no runtime data/media or screenshot attachments are staged.
6. Commit with a message such as:

```bash
git add docs/PROJECT_STATUS.md docs/plans/2026-04-26-inline-detail-editing-and-public-import-positioning.md [implementation files]
git commit -m "feat: streamline detail editing and import positioning"
```

**Verification commands:**

```bash
. .venv/bin/activate && python -m pytest -q
npm run build
git diff --check
git status --short
```
