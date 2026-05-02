# Search, Sort, and Lightweight Query Syntax Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add clear sorting controls and lightweight structured query syntax to the Image Prompt Library search bar while preserving today's plain keyword search behavior.

**Architecture:** Keep one search box for both human keywords and structured filters. Parse supported `key:value` tokens out of the search string, keep all remaining text as normal full-text keywords, and apply everything with AND semantics. Sorting should be an explicit UI control backed by the existing `/api/items?sort=...` parameter.

**Tech Stack:** FastAPI, SQLite/FTS, React/Vite, TypeScript.

---

## Product behavior

### Current behavior to preserve

- Plain search text continues to search across item titles, prompt text, tags, collections, sources, and notes.
- Search continues to work together with the existing collection filter.
- Unknown syntax should not break normal search; unsupported `key:value` tokens should be treated as plain keyword text until explicitly supported.

### New query syntax MVP

Supported examples:

```text
created:today apple
created:7d poster
updated:today tag:ecommerce
source:awesome-gpt-image-2 glasses
model:gpt-image-2 packaging
fav:true cat
has:image apple
```

Rules:

- `key:value` tokens become structured filters only for supported keys.
- All remaining text becomes the normal keyword query.
- Structured filters and keyword text are combined with AND.
- Commas are optional separators, so `created:today, apple` behaves like `created:today apple`.
- Unknown keys remain part of keyword search in the first version.
- No OR, parentheses, nested expressions, or saved searches in the MVP.

Initial supported keys:

- `created:today`, `created:yesterday`, `created:7d`, `created:30d`
- `updated:today`, `updated:yesterday`, `updated:7d`, `updated:30d`
- `model:<text>`
- `source:<text>`
- `tag:<text>`
- `fav:true|false`
- `has:image`, `has:prompt`, `has:reference`, `has:generation`

### Sorting MVP

Add a visible sort control. Suggested options:

- Recently updated — default for local app
- Recently created
- Oldest created
- Title A–Z
- Title Z–A
- Source
- Model

Public demo can keep a stable default if needed, but the same control should work when demo data supports it.

---

## README guidance

Document current search separately from planned syntax so users are not misled before implementation ships:

- Current release: keyword search plus collection filter.
- Planned release: examples like `created:today apple` and explicit sort dropdown.

After implementation ships, update README examples to say these query filters are available.

---

## Task 1: Add backend query parser tests

**Objective:** Define how mixed keyword + structured query text is parsed.

**Files:**

- Create: `backend/services/search_query.py`
- Test: `tests/test_search_query.py`

**Cases:**

- `created:today apple` -> filters `{created: today}`, keyword `apple`
- `created:today, apple` -> same as above
- `model:gpt-image-2 packaging` -> model filter + keyword
- `creator:john apple` -> unsupported key remains keyword text
- empty/whitespace query -> no filters, empty keyword

**Verification:**

```bash
pytest tests/test_search_query.py -q
```

Expected: parser tests pass.

---

## Task 2: Extend repository filtering

**Objective:** Support parsed filters in `ItemRepository.list_items` without breaking existing `q`, `cluster`, `tag`, `favorite`, `archived`, `limit`, or `offset` behavior.

**Files:**

- Modify: `backend/repositories.py`
- Modify: `backend/routers/items.py`
- Test: existing item repository/API tests, plus new focused tests if needed

**Implementation notes:**

- Parse `q` at the API/repository boundary.
- Use the remaining keyword text for the current FTS/LIKE search logic.
- Add date range helpers for UTC `created_at` / `updated_at` comparisons.
- Add model/source/tag/favorite/has filters as SQL clauses.
- Keep unsupported keys inside keyword text.

**Verification:**

```bash
pytest tests/test_public_mvp.py tests/test_sample_data_bundle.py -q
```

Add a focused query-filter test if no existing test covers `/api/items` search behavior.

---

## Task 3: Expand sort options backend-side

**Objective:** Add stable SQL ordering for the sort dropdown.

**Files:**

- Modify: `backend/repositories.py`
- Modify: `backend/routers/items.py`
- Test: focused repository/API sort tests

**Sort keys:**

- `updated_desc`
- `created_desc`
- `created_asc`
- `title_asc`
- `title_desc`
- `source_asc`
- `model_asc`

**Verification:**

```bash
pytest tests -q
```

Expected: all backend tests pass.

---

## Task 4: Add frontend sort control

**Objective:** Let users choose sorting without cluttering the mobile UI.

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/hooks/useItemsQuery.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/TopBar.tsx` or create a compact `SortMenu` component
- Modify: `frontend/src/utils/i18n.ts`

**UX:**

- Desktop: compact sort dropdown/chip near search/status row.
- Mobile: sort chip/button that can open a small menu/bottom-sheet style control.
- Default: `updated_desc` for local app unless demo mode intentionally uses a stable default.

**Verification:**

```bash
npm run build
```

Expected: frontend build passes.

---

## Task 5: Show parsed filter chips

**Objective:** Make structured filters visible so users know `created:today apple` is being interpreted as a date filter plus keyword.

**Files:**

- Modify or create frontend query parser mirror, or return parsed metadata from API if preferred.
- Modify: `frontend/src/components/TopBar.tsx`
- Modify: `frontend/src/utils/i18n.ts`

**UX:**

- Show chips such as `created: today`, `model: gpt-image-2`, and `keyword: apple`.
- Keep chip display compact on mobile.
- Removing a chip can be a later enhancement; MVP may be display-only.

**Verification:**

```bash
npm run build
```

---

## Task 6: Update README after implementation

**Objective:** Teach users how to use search and sorting.

**Files:**

- Modify: `README.md`

**Add examples:**

```text
apple
created:today apple
created:7d model:gpt-image-2 poster
updated:today tag:ecommerce
source:awesome-gpt-image-2 glasses
fav:true cat
has:image packaging
```

**Verification:**

```bash
pytest -q
npm run build
```

Expected: docs-related static tests and frontend build pass.
