# Library Power-User Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved Library Power-User Polish milestone: clearer search/sort/filter state, backend-backed batch management, and preview-first cleanup for local libraries.

**Architecture:** Reuse the existing FastAPI `ItemRepository` and React/Vite single-app flow. Keep query parsing small and deterministic, keep batch actions server-side but backed by existing item mutation methods, and keep cleanup preview-first with known library media directories only.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, SQLite/FTS5, pytest, React 19, TypeScript, Vite, native HTML controls.

---

## Scope Guard

This plan implements B: Library Power-User Polish. It does not implement install/onboarding work, generation-provider hardening, or external import adapters.

Ponytail constraints for implementation:

- No new dependencies.
- No full query language.
- No saved searches.
- No admin dashboard.
- No background cleanup worker.
- No metadata migration.
- Defer generation staging deletion unless existing database references prove safety during Task 6.

## File Structure

Create:

- `backend/services/search_query.py`: parse supported `key:value` search tokens into a typed item-search structure.
- `backend/services/library_cleanup.py`: preview and apply safe cleanup for broken image records and unreferenced known media files.
- `backend/routers/cleanup.py`: expose cleanup preview/apply endpoints.
- `tests/test_search_query.py`: unit tests for backend query parsing.
- `tests/test_cleanup_api.py`: API tests for cleanup preview/apply safety.

Modify:

- `backend/repositories.py`: apply parsed query filters, extra sort modes, and batch item actions.
- `backend/routers/items.py`: expose batch item endpoint and keep existing item endpoints compatible.
- `backend/schemas.py`: add batch and cleanup request/response models.
- `backend/main.py`: register cleanup router.
- `frontend/src/types.ts`: add sort modes, batch result/request types, cleanup types.
- `frontend/src/utils/searchSort.ts`: mirror query parsing enough for chips and visible sort labels.
- `frontend/src/hooks/useItemsQuery.ts`: keep taking a sort mode and send the active visible sort.
- `frontend/src/api/client.ts`: add batch/cleanup client methods and static-demo query support.
- `frontend/src/components/TopBar.tsx`: add native visible sort control and active chips.
- `frontend/src/App.tsx`: own visible sort state, call batch API, refresh after batch/cleanup.
- `frontend/src/components/ConfigPanel.tsx`: add local-only cleanup section.
- `frontend/src/utils/i18n.ts`: add labels for new controls.
- `frontend/src/styles.css`: compact styles for sort control, batch toolbar additions, cleanup section.
- `tests/test_items_api.py`: add backend item filter/sort and batch API coverage.
- `tests/test_frontend_static.py`: update old sort expectations and add static checks for batch/cleanup UI.

---

### Task 1: Backend Search Query Parser

**Files:**
- Create: `backend/services/search_query.py`
- Create: `tests/test_search_query.py`

- [ ] **Step 1: Write parser tests**

Create `tests/test_search_query.py`:

```python
from backend.services.search_query import parse_item_search_query


def test_plain_keyword_search_stays_plain():
    parsed = parse_item_search_query("apple packaging")
    assert parsed.keyword == "apple packaging"
    assert parsed.created is None
    assert parsed.updated is None
    assert parsed.tags == []
    assert parsed.collections == []
    assert parsed.models == []
    assert parsed.sources == []
    assert parsed.favorite is None
    assert parsed.has == set()


def test_supported_filters_are_removed_from_keyword_text():
    parsed = parse_item_search_query("created:7d tag:template source:awesome packaging")
    assert parsed.keyword == "packaging"
    assert parsed.created == "7d"
    assert parsed.tags == ["template"]
    assert parsed.sources == ["awesome"]


def test_commas_are_optional_separators():
    parsed = parse_item_search_query("created:today, apple")
    assert parsed.keyword == "apple"
    assert parsed.created == "today"


def test_unknown_keys_remain_keywords():
    parsed = parse_item_search_query("creator:edward apple")
    assert parsed.keyword == "creator:edward apple"
    assert parsed.tags == []


def test_boolean_and_has_filters():
    parsed = parse_item_search_query("fav:true has:image has:reference cat")
    assert parsed.keyword == "cat"
    assert parsed.favorite is True
    assert parsed.has == {"image", "reference"}


def test_invalid_filter_values_remain_keywords():
    parsed = parse_item_search_query("created:forever fav:maybe has:video apple")
    assert parsed.keyword == "created:forever fav:maybe has:video apple"
    assert parsed.created is None
    assert parsed.favorite is None
    assert parsed.has == set()
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
python -m pytest tests/test_search_query.py -q
```

Expected: FAIL because `backend.services.search_query` does not exist.

- [ ] **Step 3: Implement the parser**

Create `backend/services/search_query.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

DATE_VALUES = {"today", "yesterday", "7d", "30d"}
HAS_VALUES = {"image", "result", "reference", "prompt"}
TOKEN_RE = re.compile(r"[^,\s]+")


@dataclass(frozen=True)
class ParsedItemSearchQuery:
    keyword: str = ""
    created: str | None = None
    updated: str | None = None
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    favorite: bool | None = None
    has: set[str] = field(default_factory=set)


def _append_unique(values: list[str], value: str) -> list[str]:
    if value and value not in values:
        values.append(value)
    return values


def parse_item_search_query(raw_query: str | None) -> ParsedItemSearchQuery:
    if not raw_query or not raw_query.strip():
        return ParsedItemSearchQuery()

    keyword_parts: list[str] = []
    created: str | None = None
    updated: str | None = None
    tags: list[str] = []
    collections: list[str] = []
    models: list[str] = []
    sources: list[str] = []
    favorite: bool | None = None
    has: set[str] = set()

    for match in TOKEN_RE.finditer(raw_query):
        token = match.group(0).strip()
        key, sep, value = token.partition(":")
        key = key.lower()
        value = value.strip()
        value_lower = value.lower()

        consumed = True
        if sep != ":" or not key or not value:
            consumed = False
        elif key == "created" and value_lower in DATE_VALUES:
            created = value_lower
        elif key == "updated" and value_lower in DATE_VALUES:
            updated = value_lower
        elif key == "tag":
            tags = _append_unique(tags, value)
        elif key == "collection":
            collections = _append_unique(collections, value)
        elif key == "model":
            models = _append_unique(models, value)
        elif key == "source":
            sources = _append_unique(sources, value)
        elif key in {"fav", "favorite"} and value_lower in {"true", "false"}:
            favorite = value_lower == "true"
        elif key == "has" and value_lower in HAS_VALUES:
            has.add(value_lower)
        else:
            consumed = False

        if not consumed:
            keyword_parts.append(token)

    return ParsedItemSearchQuery(
        keyword=" ".join(keyword_parts).strip(),
        created=created,
        updated=updated,
        tags=tags,
        collections=collections,
        models=models,
        sources=sources,
        favorite=favorite,
        has=has,
    )
```

- [ ] **Step 4: Verify parser tests pass**

Run:

```bash
python -m pytest tests/test_search_query.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit parser slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add backend/services/search_query.py tests/test_search_query.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: add item search query parser"
```

Expected: commit succeeds.

---

### Task 2: Backend Item Filtering and Sort Modes

**Files:**
- Modify: `backend/repositories.py`
- Modify: `backend/routers/items.py`
- Modify: `backend/schemas.py`
- Test: `tests/test_items_api.py`

- [ ] **Step 1: Add API tests for structured filters and sort modes**

Append to `tests/test_items_api.py`:

```python
def test_structured_query_filters_keywords_and_has_filters(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    apple = c.post("/api/items", json=create_payload(
        title="Apple Package",
        cluster_name="Packaging",
        tags=["template", "fruit"],
        model="gpt-image-2",
        source_name="awesome-gpt-image-2",
        source_url="https://example.test/apple",
    )).json()
    poster = c.post("/api/items", json=create_payload(
        title="Poster Study",
        cluster_name="Poster",
        tags=["poster"],
        model="other-model",
        source_name="manual",
        source_url="https://example.test/poster",
    )).json()
    c.post(
        f"/api/items/{apple['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
    c.post(
        f"/api/items/{poster['id']}/images",
        data={"role": "reference_image"},
        files={"file": ("reference.png", png_bytes(color=(1, 2, 3)), "image/png")},
    )
    with connect(library) as conn:
        conn.execute("UPDATE items SET created_at=?, updated_at=? WHERE id=?", ("2000-01-01T01:00:00+00:00", "2000-01-01T02:00:00+00:00", poster["id"]))
        conn.commit()

    assert c.get("/api/items", params={"q": "tag:template apple"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "collection:Packaging apple"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "model:gpt-image-2 source:awesome apple"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "created:30d apple"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "has:result apple"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "has:reference apple"}).json()["total"] == 0
    assert c.get("/api/items", params={"q": "creator:edward apple"}).json()["total"] == 0


def test_extended_item_sort_modes(tmp_path):
    c = client(tmp_path)
    alpha = c.post("/api/items", json=create_payload(title="Alpha Sort", model="Model B", source_name="Source B", source_url="https://example.test/alpha")).json()
    beta = c.post("/api/items", json=create_payload(title="Beta Sort", model="Model A", source_name="Source C", source_url="https://example.test/beta")).json()
    gamma = c.post("/api/items", json=create_payload(title="Gamma Sort", model="Model C", source_name="Source A", source_url="https://example.test/gamma")).json()
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE items SET created_at=?, updated_at=? WHERE id=?", ("2026-01-01T00:00:00+00:00", "2026-01-04T00:00:00+00:00", alpha["id"]))
        conn.execute("UPDATE items SET created_at=?, updated_at=? WHERE id=?", ("2026-01-02T00:00:00+00:00", "2026-01-03T00:00:00+00:00", beta["id"]))
        conn.execute("UPDATE items SET created_at=?, updated_at=? WHERE id=?", ("2026-01-03T00:00:00+00:00", "2026-01-02T00:00:00+00:00", gamma["id"]))
        conn.commit()

    assert [item["title"] for item in c.get("/api/items", params={"sort": "created_asc"}).json()["items"]] == ["Alpha Sort", "Beta Sort", "Gamma Sort"]
    assert [item["title"] for item in c.get("/api/items", params={"sort": "title_desc"}).json()["items"]] == ["Gamma Sort", "Beta Sort", "Alpha Sort"]
    assert [item["title"] for item in c.get("/api/items", params={"sort": "source_asc"}).json()["items"]] == ["Gamma Sort", "Alpha Sort", "Beta Sort"]
    assert [item["title"] for item in c.get("/api/items", params={"sort": "model_asc"}).json()["items"]] == ["Beta Sort", "Alpha Sort", "Gamma Sort"]
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
python -m pytest tests/test_items_api.py::test_structured_query_filters_keywords_and_has_filters tests/test_items_api.py::test_extended_item_sort_modes -q
```

Expected: FAIL because structured filters and new sort modes are not implemented.

- [ ] **Step 3: Extend backend types and repository filtering**

In `backend/schemas.py`, add near `ItemList`:

```python
class ItemBatchResult(BaseModel):
    requested: int
    changed: int
    skipped: int = 0
    failed: int = 0
    item_ids: List[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
```

The batch result is added now because Task 4 will use the same schema file; no route uses it until Task 4.

In `backend/repositories.py`:

- Import parser and datetime helpers:

```python
from datetime import datetime, timezone, timedelta
from .services.search_query import parse_item_search_query
```

- Replace the existing `from datetime import datetime, timezone` import with the combined import above.

- Add helper method inside `ItemRepository` before `list_items`:

```python
    def _date_filter_window(self, value: str) -> tuple[str, str | None]:
        current = datetime.now(timezone.utc)
        today = current.replace(hour=0, minute=0, second=0, microsecond=0)
        if value == "today":
            return today.isoformat(), None
        if value == "yesterday":
            return (today - timedelta(days=1)).isoformat(), today.isoformat()
        if value == "7d":
            return (current - timedelta(days=7)).isoformat(), None
        if value == "30d":
            return (current - timedelta(days=30)).isoformat(), None
        return current.isoformat(), None
```

- In `list_items`, parse `q` first:

```python
        parsed_query = parse_item_search_query(q)
        q = parsed_query.keyword
```

- Add SQL clauses after the existing `favorite` clause:

```python
        if parsed_query.favorite is not None:
            where.append("i.favorite=?")
            params.append(int(parsed_query.favorite))
        if parsed_query.created:
            start, end = self._date_filter_window(parsed_query.created)
            where.append("i.created_at>=?")
            params.append(start)
            if end:
                where.append("i.created_at<?")
                params.append(end)
        if parsed_query.updated:
            start, end = self._date_filter_window(parsed_query.updated)
            where.append("i.updated_at>=?")
            params.append(start)
            if end:
                where.append("i.updated_at<?")
                params.append(end)
        for value in parsed_query.tags:
            where.append("EXISTS (SELECT 1 FROM item_tags qit JOIN tags qt ON qt.id=qit.tag_id WHERE qit.item_id=i.id AND qt.name LIKE ?)")
            params.append(f"%{value}%")
        for value in parsed_query.collections:
            where.append("c.name LIKE ?")
            params.append(f"%{value}%")
        for value in parsed_query.models:
            where.append("i.model LIKE ?")
            params.append(f"%{value}%")
        for value in parsed_query.sources:
            where.append("(i.source_name LIKE ? OR i.source_url LIKE ?)")
            params += [f"%{value}%", f"%{value}%"]
        if "image" in parsed_query.has:
            where.append("EXISTS (SELECT 1 FROM images qi WHERE qi.item_id=i.id)")
        if "result" in parsed_query.has:
            where.append("EXISTS (SELECT 1 FROM images qi WHERE qi.item_id=i.id AND qi.role='result_image')")
        if "reference" in parsed_query.has:
            where.append("EXISTS (SELECT 1 FROM images qi WHERE qi.item_id=i.id AND qi.role='reference_image')")
        if "prompt" in parsed_query.has:
            where.append("EXISTS (SELECT 1 FROM prompts qp WHERE qp.item_id=i.id AND TRIM(qp.text)!='')")
```

- Extend the sort map:

```python
        order = {
            "created_desc": "i.created_at DESC",
            "created_asc": "i.created_at ASC",
            "title_asc": "i.title COLLATE NOCASE ASC",
            "title_desc": "i.title COLLATE NOCASE DESC",
            "source_asc": "COALESCE(i.source_name, '') COLLATE NOCASE ASC, i.title COLLATE NOCASE ASC",
            "model_asc": "i.model COLLATE NOCASE ASC, i.title COLLATE NOCASE ASC",
            "rating_desc": "i.rating DESC, i.updated_at DESC",
        }.get(sort, "i.updated_at DESC")
```

- [ ] **Step 4: Verify backend item tests pass**

Run:

```bash
python -m pytest tests/test_search_query.py tests/test_items_api.py::test_create_get_search_and_filter_item tests/test_items_api.py::test_item_list_sorts_by_created_and_title_without_rating_ui tests/test_items_api.py::test_structured_query_filters_keywords_and_has_filters tests/test_items_api.py::test_extended_item_sort_modes -q
```

Expected: PASS.

- [ ] **Step 5: Commit backend search/filter slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add backend/repositories.py backend/schemas.py tests/test_items_api.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: support structured item filters"
```

Expected: commit succeeds.

---

### Task 3: Visible Sort Control and Active Chips

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/utils/searchSort.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useItemsQuery.ts`
- Modify: `frontend/src/components/TopBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/utils/i18n.ts`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Update static frontend test expectations**

In `tests/test_frontend_static.py`, replace `test_search_bar_supports_sort_operators_without_extra_dropdown_ui` with:

```python
def test_search_bar_has_visible_sort_control_and_query_filter_chips():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    search_sort = (ROOT / "frontend" / "src" / "utils" / "searchSort.ts").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "const [sort, setSort]" in app
    assert "const activeSort = parsedSearchQuery.explicitSort ? parsedSearchQuery.sort : sort" in app
    assert "useItemsQuery(parsedSearchQuery.q, clusterId, undefined, 1000, itemsReloadKey, activeSort)" in app
    assert "onSort={updateSort}" in app
    assert "sort: ItemSortMode = DEFAULT_ITEM_SORT" in hook
    assert "api.items({ q, cluster: clusterId, tag, limit: viewLimit, sort })" in hook
    assert "sort-select" in topbar
    assert "value={sort}" in topbar
    assert "onChange={event => onSort(event.currentTarget.value as ItemSortMode)}" in topbar
    assert "queryFilterChips" in topbar
    assert "sort:title" in search_sort and "title_asc" in search_sort
    assert "created_asc" in search_sort and "title_desc" in search_sort
    assert "parseSearchSortQuery" in search_sort
    assert "parseStructuredSearchChips" in search_sort
    assert "sortByOldest" in i18n
    assert "sortByTitleDesc" in i18n
    assert "sortBySource" in i18n
    assert "sortByModel" in i18n
    assert "demoItemSort" in client
    assert "demoStructuredSearch" in client
```

- [ ] **Step 2: Run static test and confirm failure**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_search_bar_has_visible_sort_control_and_query_filter_chips -q
```

Expected: FAIL because the visible sort control and chip parser do not exist yet.

- [ ] **Step 3: Extend frontend types**

In `frontend/src/types.ts`, replace:

```ts
export type ItemSortMode = 'updated_desc' | 'created_desc' | 'title_asc'
```

with:

```ts
export type ItemSortMode = 'updated_desc' | 'created_desc' | 'created_asc' | 'title_asc' | 'title_desc' | 'source_asc' | 'model_asc'
```

- [ ] **Step 4: Extend `searchSort.ts`**

Update `frontend/src/utils/searchSort.ts` so it includes:

```ts
const SORT_OPERATOR_RE = /(?:^|\s)sort:(updated|created|oldest|title|title-desc|source|model)(?=\s|$)/gi;

const SORT_OPERATORS: Record<string, ItemSortMode> = {
  'sort:updated': 'updated_desc',
  'sort:created': 'created_desc',
  'sort:oldest': 'created_asc',
  'sort:title': 'title_asc',
  'sort:title-desc': 'title_desc',
  'sort:source': 'source_asc',
  'sort:model': 'model_asc',
};

const STRUCTURED_FILTER_RE = /(?:^|[\s,])((created|updated|tag|collection|model|source|fav|favorite|has):[^\s,]+)/gi;

export function parseStructuredSearchChips(rawQuery: string) {
  const chips: string[] = [];
  rawQuery.replace(STRUCTURED_FILTER_RE, (_match, token) => {
    const [key, value] = String(token).split(':', 2);
    if (!key || !value) return '';
    const normalizedKey = key.toLowerCase();
    const normalizedValue = value.trim();
    const supported =
      ['tag', 'collection', 'model', 'source'].includes(normalizedKey) ||
      (['created', 'updated'].includes(normalizedKey) && ['today', 'yesterday', '7d', '30d'].includes(normalizedValue.toLowerCase())) ||
      (['fav', 'favorite'].includes(normalizedKey) && ['true', 'false'].includes(normalizedValue.toLowerCase())) ||
      (normalizedKey === 'has' && ['image', 'result', 'reference', 'prompt'].includes(normalizedValue.toLowerCase()));
    if (supported) chips.push(`${normalizedKey}: ${normalizedValue}`);
    return '';
  });
  return chips;
}

export function sortLabelForMode(sort: ItemSortMode, t: Translator) {
  if (sort === 'created_desc') return t('sortByCreated');
  if (sort === 'created_asc') return t('sortByOldest');
  if (sort === 'title_asc') return t('sortByTitle');
  if (sort === 'title_desc') return t('sortByTitleDesc');
  if (sort === 'source_asc') return t('sortBySource');
  if (sort === 'model_asc') return t('sortByModel');
  return t('sortByUpdated');
}
```

Keep existing `parseSearchSortQuery` and `removeSearchSortOperator`, but let them use the expanded `SORT_OPERATOR_RE`.

- [ ] **Step 5: Add demo sorting and simple demo filter support**

In `frontend/src/api/client.ts`, update `demoItemSort`:

```ts
function demoItemSort(sort: ItemSortMode) {
  if (sort === 'created_desc') return (a: ItemSummary, b: ItemSummary) => b.created_at.localeCompare(a.created_at);
  if (sort === 'created_asc') return (a: ItemSummary, b: ItemSummary) => a.created_at.localeCompare(b.created_at);
  if (sort === 'title_asc') return (a: ItemSummary, b: ItemSummary) => a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });
  if (sort === 'title_desc') return (a: ItemSummary, b: ItemSummary) => b.title.localeCompare(a.title, undefined, { sensitivity: 'base' });
  if (sort === 'source_asc') return (a: ItemSummary, b: ItemSummary) => (a.source_name || '').localeCompare(b.source_name || '', undefined, { sensitivity: 'base' }) || a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });
  if (sort === 'model_asc') return (a: ItemSummary, b: ItemSummary) => a.model.localeCompare(b.model, undefined, { sensitivity: 'base' }) || a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });
  return (a: ItemSummary, b: ItemSummary) => b.updated_at.localeCompare(a.updated_at);
}
```

Add a small `demoStructuredSearch` helper above `demoItemList`:

```ts
function demoStructuredSearch(raw: string) {
  const tokens = raw.split(/[\s,]+/).filter(Boolean);
  const filters: Record<string, string[]> = {};
  const keywords: string[] = [];
  tokens.forEach(token => {
    const [key, value] = token.split(':', 2);
    const normalizedKey = key?.toLowerCase();
    if (value && ['tag', 'collection', 'model', 'source', 'fav', 'favorite', 'has'].includes(normalizedKey)) {
      filters[normalizedKey] = [...(filters[normalizedKey] || []), value];
    } else {
      keywords.push(token);
    }
  });
  return { filters, keyword: keywords.join(' ').trim().toLowerCase() };
}
```

Use it in `demoItemList`:

```ts
  const structured = demoStructuredSearch(String(params.q || '').trim());
  const q = structured.keyword;
```

Add simple filter checks inside `filtered`:

```ts
    if (structured.filters.tag?.some(value => !item.tags.some(itemTag => itemTag.name.toLowerCase().includes(value.toLowerCase())))) return false;
    if (structured.filters.collection?.some(value => !(item.cluster?.name || '').toLowerCase().includes(value.toLowerCase()))) return false;
    if (structured.filters.model?.some(value => !item.model.toLowerCase().includes(value.toLowerCase()))) return false;
    if (structured.filters.source?.some(value => !`${item.source_name || ''} ${item.source_url || ''}`.toLowerCase().includes(value.toLowerCase()))) return false;
    if (structured.filters.has?.includes('image') && !item.first_image) return false;
    if (structured.filters.fav?.includes('true') && !item.favorite) return false;
    if (structured.filters.favorite?.includes('true') && !item.favorite) return false;
```

Do not implement demo date filters in this slice; the local backend is authoritative for date filtering.

- [ ] **Step 6: Add visible sort control to TopBar**

In `frontend/src/components/TopBar.tsx`:

- Import `ItemSortMode` and `DEFAULT_ITEM_SORT`.
- Add props:

```ts
  sort: ItemSortMode;
  queryFilterChips?: string[];
  onSort: (sort: ItemSortMode) => void;
```

- Add this native select near the active filter strip:

```tsx
          <label className="sort-select-label">
            <span>{t('sortChip')}</span>
            <select className="sort-select" value={sort} onChange={event => onSort(event.currentTarget.value as ItemSortMode)}>
              <option value="updated_desc">{t('sortByUpdated')}</option>
              <option value="created_desc">{t('sortByCreated')}</option>
              <option value="created_asc">{t('sortByOldest')}</option>
              <option value="title_asc">{t('sortByTitle')}</option>
              <option value="title_desc">{t('sortByTitleDesc')}</option>
              <option value="source_asc">{t('sortBySource')}</option>
              <option value="model_asc">{t('sortByModel')}</option>
            </select>
          </label>
```

- Render structured filter chips:

```tsx
          {queryFilterChips?.map(chip => <span key={chip} className="chip soft-chip query-filter-chip">{chip}</span>)}
```

- Keep the old sort chip only for query-token sort overrides:

```tsx
          {sortLabel && sort !== DEFAULT_ITEM_SORT && onClearSort && <button className="chip active-filter sort-chip" onClick={onClearSort}>{t('sortChip')}: {sortLabel} x</button>}
```

- [ ] **Step 7: Wire sort state in App**

In `frontend/src/App.tsx`:

- Import `parseStructuredSearchChips`.
- Add:

```ts
  const [sort, setSort] = useState<ItemSortMode>(DEFAULT_ITEM_SORT);
```

- Add:

```ts
  const activeSort = parsedSearchQuery.explicitSort ? parsedSearchQuery.sort : sort;
  const queryFilterChips = useMemo(() => parseStructuredSearchChips(debouncedQ), [debouncedQ]);
```

- Use:

```ts
  const { data, loading, initialLoading, refreshing, error, dataScope } = useItemsQuery(parsedSearchQuery.q, clusterId, undefined, 1000, itemsReloadKey, activeSort);
```

- Add:

```ts
  const updateSort = (nextSort: ItemSortMode) => {
    setSort(nextSort);
    setQ(current => removeSearchSortOperator(current));
  };
```

- Replace the existing `clearSearchSort` implementation with:

```ts
  const clearSearchSort = () => {
    setSort(DEFAULT_ITEM_SORT);
    setQ(current => removeSearchSortOperator(current));
  };
```

- Pass `sort={activeSort}`, `queryFilterChips={queryFilterChips}`, and `onSort={updateSort}` into `TopBar`.

- [ ] **Step 8: Add i18n keys and basic CSS**

In `frontend/src/utils/i18n.ts`, extend `TranslationKey`:

```ts
  | 'sortByOldest' | 'sortByTitleDesc' | 'sortBySource' | 'sortByModel'
```

Add English labels:

```ts
sortByOldest: 'Oldest added', sortByTitleDesc: 'Title Z-A', sortBySource: 'Source', sortByModel: 'Model',
```

Add equivalent labels to `zh_hant` and `zh_hans`. If the existing localized text is mojibake in this checkout, keep ASCII fallback labels for these new keys to avoid corrupting more existing strings.

In `frontend/src/styles.css`, add compact styles:

```css
.sort-select-label{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:800;color:#5b5060}.sort-select{border:1px solid rgba(33,25,34,.16);border-radius:999px;background:white;padding:6px 28px 6px 10px;font:inherit;color:#211922}.query-filter-chip{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
```

- [ ] **Step 9: Verify frontend sort/chip slice**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_search_bar_has_visible_sort_control_and_query_filter_chips -q
npm run build
```

Expected: both PASS.

- [ ] **Step 10: Commit frontend sort/chip slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add frontend/src/types.ts frontend/src/utils/searchSort.ts frontend/src/api/client.ts frontend/src/components/TopBar.tsx frontend/src/App.tsx frontend/src/utils/i18n.ts frontend/src/styles.css tests/test_frontend_static.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: add visible item sort controls"
```

Expected: commit succeeds.

---

### Task 4: Backend Batch Item Actions

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/repositories.py`
- Modify: `backend/routers/items.py`
- Test: `tests/test_items_api.py`

- [ ] **Step 1: Add batch API tests**

Append to `tests/test_items_api.py`:

```python
def test_batch_archive_favorite_tag_and_move_items(tmp_path):
    c = client(tmp_path)
    first = c.post("/api/items", json=create_payload(title="Batch One", source_url="https://example.test/batch-one")).json()
    second = c.post("/api/items", json=create_payload(title="Batch Two", source_url="https://example.test/batch-two")).json()

    archived = c.post("/api/items/batch", json={"item_ids": [first["id"], second["id"]], "action": "archive"}).json()
    assert archived["requested"] == 2
    assert archived["changed"] == 2
    assert c.get("/api/items").json()["total"] == 0
    assert c.get("/api/items", params={"archived": True}).json()["total"] == 2

    unarchived = c.post("/api/items/batch", json={"item_ids": [first["id"], second["id"]], "action": "unarchive"}).json()
    assert unarchived["changed"] == 2
    assert c.get("/api/items").json()["total"] == 2

    favorite = c.post("/api/items/batch", json={"item_ids": [first["id"], second["id"]], "action": "favorite"}).json()
    assert favorite["changed"] == 2
    assert c.get("/api/items", params={"favorite": True}).json()["total"] == 2

    tagged = c.post("/api/items/batch", json={"item_ids": [first["id"], second["id"]], "action": "add_tags", "tags": ["batch", "cleanup"]}).json()
    assert tagged["changed"] == 2
    assert c.get("/api/items", params={"q": "tag:batch"}).json()["total"] == 2

    moved = c.post("/api/items/batch", json={"item_ids": [first["id"], second["id"]], "action": "move_collection", "cluster_name": "Batch Review"}).json()
    assert moved["changed"] == 2
    assert c.get("/api/items", params={"q": "collection:Batch"}).json()["total"] == 2

    removed = c.post("/api/items/batch", json={"item_ids": [first["id"], second["id"]], "action": "remove_tags", "tags": ["cleanup"]}).json()
    assert removed["changed"] == 2
    assert c.get("/api/items", params={"q": "tag:cleanup"}).json()["total"] == 0


def test_batch_delete_uses_server_side_delete_and_reports_missing_items(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    item = c.post("/api/items", json=create_payload(title="Batch Delete")).json()
    uploaded = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    ).json()
    stored_paths = [library / uploaded[key] for key in ("original_path", "thumb_path", "preview_path")]
    result = c.post("/api/items/batch", json={"item_ids": [item["id"], "missing"], "action": "delete"}).json()

    assert result["requested"] == 2
    assert result["changed"] == 1
    assert result["failed"] == 1
    assert "missing" in result["errors"]
    assert c.get("/api/items").json()["total"] == 0
    assert all(not path.exists() for path in stored_paths)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
python -m pytest tests/test_items_api.py::test_batch_archive_favorite_tag_and_move_items tests/test_items_api.py::test_batch_delete_uses_server_side_delete_and_reports_missing_items -q
```

Expected: FAIL because `/api/items/batch` does not exist.

- [ ] **Step 3: Add schemas**

In `backend/schemas.py`, extend imports:

```python
from typing import Any, List, Optional, Literal
```

Add after `ItemBatchResult` from Task 2:

```python
class ItemBatchRequest(BaseModel):
    item_ids: List[str] = Field(min_length=1, max_length=500)
    action: Literal["delete", "archive", "unarchive", "favorite", "unfavorite", "add_tags", "remove_tags", "move_collection"]
    tags: List[str] = Field(default_factory=list)
    cluster_id: Optional[str] = None
    cluster_name: Optional[str] = None
```

- [ ] **Step 4: Add repository batch method**

In `backend/repositories.py`, add helper methods inside `ItemRepository`:

```python
    def _tag_names_for_item(self, conn, item_id: str) -> list[str]:
        return [row["name"] for row in conn.execute(
            "SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id=t.id WHERE it.item_id=? ORDER BY t.name",
            (item_id,),
        ).fetchall()]

    def batch_items(self, item_ids: list[str], action: str, *, tags: list[str] | None = None, cluster_id: str | None = None, cluster_name: str | None = None) -> dict:
        changed: list[str] = []
        errors: dict[str, str] = {}
        clean_tags = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
        for item_id in item_ids:
            try:
                if action == "delete":
                    self.delete_item(item_id)
                elif action == "archive":
                    self.update_item(item_id, ItemUpdate(archived=True))
                elif action == "unarchive":
                    self.update_item(item_id, ItemUpdate(archived=False))
                elif action == "favorite":
                    self.update_item(item_id, ItemUpdate(favorite=True))
                elif action == "unfavorite":
                    self.update_item(item_id, ItemUpdate(favorite=False))
                elif action == "add_tags":
                    current = self.get_item(item_id)
                    next_tags = list(dict.fromkeys([tag.name for tag in current.tags] + clean_tags))
                    self.update_item(item_id, ItemUpdate(tags=next_tags))
                elif action == "remove_tags":
                    remove = set(clean_tags)
                    current = self.get_item(item_id)
                    next_tags = [tag.name for tag in current.tags if tag.name not in remove]
                    self.update_item(item_id, ItemUpdate(tags=next_tags))
                elif action == "move_collection":
                    self.update_item(item_id, ItemUpdate(cluster_id=cluster_id, cluster_name=cluster_name))
                else:
                    errors[item_id] = f"Unsupported batch action: {action}"
                    continue
                changed.append(item_id)
            except KeyError:
                errors[item_id] = "Item not found"
            except ValueError as exc:
                errors[item_id] = str(exc)
        return {
            "requested": len(item_ids),
            "changed": len(changed),
            "skipped": 0,
            "failed": len(errors),
            "item_ids": changed,
            "errors": errors,
        }
```

Remove `_tag_names_for_item` if it ends unused after implementation; do not keep dead helpers.

- [ ] **Step 5: Add route**

In `backend/routers/items.py`, update import:

```python
from backend.schemas import ItemBatchRequest, ItemBatchResult, ItemCreate, ItemDetail, ItemList, ItemUpdate
```

Add route before `@router.post("/items", response_model=ItemDetail)`:

```python
@router.post("/items/batch", response_model=ItemBatchResult)
def batch_items(request: Request, payload: ItemBatchRequest):
    if payload.action in {"add_tags", "remove_tags"} and not payload.tags:
        raise HTTPException(400, "Batch tag actions require tags")
    if payload.action == "move_collection" and not (payload.cluster_id or payload.cluster_name):
        raise HTTPException(400, "Batch move requires a collection")
    return repo(request).batch_items(
        payload.item_ids,
        payload.action,
        tags=payload.tags,
        cluster_id=payload.cluster_id,
        cluster_name=payload.cluster_name,
    )
```

- [ ] **Step 6: Verify batch API tests pass**

Run:

```bash
python -m pytest tests/test_items_api.py::test_batch_archive_favorite_tag_and_move_items tests/test_items_api.py::test_batch_delete_uses_server_side_delete_and_reports_missing_items -q
```

Expected: PASS.

- [ ] **Step 7: Commit backend batch slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add backend/schemas.py backend/repositories.py backend/routers/items.py tests/test_items_api.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: add batch item actions"
```

Expected: commit succeeds.

---

### Task 5: Frontend Batch Toolbar Actions

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/utils/i18n.ts`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Add static frontend checks for batch actions**

Append to `tests/test_frontend_static.py`:

```python
def test_selection_toolbar_uses_batch_api_for_power_user_actions():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text()

    assert "ItemBatchRequest" in types
    assert "ItemBatchResult" in types
    assert "batchItems" in api_client
    assert "api.batchItems" in app
    assert "runBatchAction" in app
    assert "batchArchiveSelected" in app
    assert "batchFavoriteSelected" in app
    assert "batchAddTagsSelected" in app
    assert "batchMoveSelected" in app
    assert "Promise.all(Array.from(selectedItemIds).map(id => api.deleteItem(id)))" not in app
    assert "selection-toolbar-secondary" in app
    assert ".selection-toolbar-secondary" in styles
```

- [ ] **Step 2: Run static test and confirm failure**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_selection_toolbar_uses_batch_api_for_power_user_actions -q
```

Expected: FAIL because frontend batch API/UI does not exist yet.

- [ ] **Step 3: Add frontend types and client**

In `frontend/src/types.ts`, add:

```ts
export type ItemBatchAction = 'delete' | 'archive' | 'unarchive' | 'favorite' | 'unfavorite' | 'add_tags' | 'remove_tags' | 'move_collection'
export interface ItemBatchRequest { item_ids: string[]; action: ItemBatchAction; tags?: string[]; cluster_id?: string; cluster_name?: string }
export interface ItemBatchResult { requested: number; changed: number; skipped: number; failed: number; item_ids: string[]; errors: Record<string, string> }
```

In `frontend/src/api/client.ts`:

- Import `ItemBatchRequest` and `ItemBatchResult`.
- In demo API:

```ts
  batchItems: (_payload: ItemBatchRequest) => demoReadOnly(),
```

- In local API:

```ts
  batchItems: (payload: ItemBatchRequest) => json<ItemBatchResult>('/api/items/batch', { method: 'POST', body: JSON.stringify(payload) }),
```

- [ ] **Step 4: Replace frontend repeated delete with batch API**

In `frontend/src/App.tsx`:

- Import `ItemBatchAction`.
- Add:

```ts
  const runBatchAction = async (action: ItemBatchAction, extra: Partial<{tags: string[]; cluster_name: string}> = {}) => {
    if (!selectedItemIds.size) return;
    try {
      const result = await api.batchItems({ item_ids: Array.from(selectedItemIds), action, ...extra });
      deleted();
      setToast({ title: `${result.changed} ${t('selectedReferences')}`, tone: result.failed ? 'error' : 'success' });
    } catch {
      setToast({ title: t('saveFailed'), tone: 'error' });
    }
  };
```

- Replace `deleteSelectedItems` body with:

```ts
  const deleteSelectedItems = async () => {
    if (!selectedItemIds.size) return;
    if (!confirm(t('deleteSelectedReferencesConfirm').replace('${selectedItemIds.size}', String(selectedItemIds.size)))) return;
    await runBatchAction('delete');
  };
```

- Add:

```ts
  const batchArchiveSelected = () => runBatchAction('archive');
  const batchFavoriteSelected = () => runBatchAction('favorite');
  const batchAddTagsSelected = () => {
    const value = window.prompt('Tags to add, comma separated');
    const tags = value?.split(',').map(tag => tag.trim()).filter(Boolean) || [];
    if (tags.length) void runBatchAction('add_tags', { tags });
  };
  const batchMoveSelected = () => {
    const cluster_name = window.prompt('Move to collection');
    if (cluster_name?.trim()) void runBatchAction('move_collection', { cluster_name: cluster_name.trim() });
  };
```

- Add toolbar buttons before delete:

```tsx
        <button type="button" className="selection-toolbar-secondary" onClick={batchArchiveSelected} disabled={!selectedItemIds.size}>{t('archiveSelectedReferences')}</button>
        <button type="button" className="selection-toolbar-secondary" onClick={batchFavoriteSelected} disabled={!selectedItemIds.size}>{t('favoriteSelectedReferences')}</button>
        <button type="button" className="selection-toolbar-secondary" onClick={batchAddTagsSelected} disabled={!selectedItemIds.size}>{t('tagSelectedReferences')}</button>
        <button type="button" className="selection-toolbar-secondary" onClick={batchMoveSelected} disabled={!selectedItemIds.size}>{t('moveSelectedReferences')}</button>
```

- [ ] **Step 5: Add labels and styles**

In `frontend/src/utils/i18n.ts`, add keys:

```ts
  | 'archiveSelectedReferences' | 'favoriteSelectedReferences' | 'tagSelectedReferences' | 'moveSelectedReferences'
```

Add English labels:

```ts
archiveSelectedReferences: 'Archive', favoriteSelectedReferences: 'Favorite', tagSelectedReferences: 'Tag', moveSelectedReferences: 'Move',
```

Add matching labels to `zh_hant` and `zh_hans`. ASCII fallback is acceptable in this mojibake checkout.

In `frontend/src/styles.css`, add:

```css
.selection-toolbar-secondary{border:0;border-radius:999px;background:rgba(255,255,255,.92);color:#211922;font-weight:850;padding:9px 12px;cursor:pointer}.selection-toolbar-secondary:disabled{opacity:.45;cursor:not-allowed}
```

- [ ] **Step 6: Verify frontend batch slice**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_selection_toolbar_uses_batch_api_for_power_user_actions -q
npm run build
```

Expected: both PASS.

- [ ] **Step 7: Commit frontend batch slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add frontend/src/types.ts frontend/src/api/client.ts frontend/src/App.tsx frontend/src/utils/i18n.ts frontend/src/styles.css tests/test_frontend_static.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: add batch management toolbar"
```

Expected: commit succeeds.

---

### Task 6: Cleanup Preview and Apply API

**Files:**
- Create: `backend/services/library_cleanup.py`
- Create: `backend/routers/cleanup.py`
- Create: `tests/test_cleanup_api.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Add cleanup API tests**

Create `tests/test_cleanup_api.py`:

```python
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from backend.db import connect
from backend.main import create_app


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def png_bytes(size=(32, 24), color=(120, 40, 220)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def create_payload(**overrides):
    payload = {
        "title": "Cleanup Fixture",
        "model": "ChatGPT Image2",
        "cluster_name": "Cleanup",
        "tags": ["cleanup"],
        "prompts": [{"language": "en", "text": "A cleanup fixture", "is_primary": True}],
        "source_name": "fixture",
        "source_url": "https://example.test/cleanup",
    }
    payload.update(overrides)
    return payload


def test_cleanup_preview_reports_broken_image_records_and_unreferenced_files(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    item = c.post("/api/items", json=create_payload()).json()
    extra = library / "originals" / "extra.png"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"extra")
    with connect(library) as conn:
        conn.execute(
            """INSERT INTO images(id,item_id,original_path,thumb_path,preview_path,role,sort_order,created_at)
               VALUES(?,?,?,?,?,?,?,datetime('now'))""",
            ("img_broken", item["id"], "originals/missing.png", None, None, "result_image", 0),
        )
        conn.commit()

    preview = c.get("/api/cleanup/preview").json()

    assert preview["broken_image_records"][0]["image_id"] == "img_broken"
    assert preview["unreferenced_files"][0]["path"] == "originals/extra.png"
    assert (library / "originals" / "extra.png").exists()
    with connect(library) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id='img_broken'").fetchone()[0] == 1


def test_cleanup_apply_removes_only_previewed_safe_records_and_files(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    item = c.post("/api/items", json=create_payload()).json()
    uploaded = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    ).json()
    extra = library / "originals" / "extra.png"
    extra.write_bytes(b"extra")
    with connect(library) as conn:
        conn.execute(
            """INSERT INTO images(id,item_id,original_path,thumb_path,preview_path,role,sort_order,created_at)
               VALUES(?,?,?,?,?,?,?,datetime('now'))""",
            ("img_broken", item["id"], "originals/missing.png", None, None, "reference_image", 1),
        )
        conn.commit()

    result = c.post("/api/cleanup/apply", json={"remove_broken_image_records": True, "remove_unreferenced_files": True}).json()

    assert result["removed_broken_image_records"] == 1
    assert result["removed_unreferenced_files"] == 1
    assert not extra.exists()
    assert (library / uploaded["original_path"]).exists()
    with connect(library) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id='img_broken'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id=?", (uploaded["id"],)).fetchone()[0] == 1
```

- [ ] **Step 2: Run cleanup tests and confirm failure**

Run:

```bash
python -m pytest tests/test_cleanup_api.py -q
```

Expected: FAIL because cleanup routes do not exist.

- [ ] **Step 3: Add schemas**

In `backend/schemas.py`, add:

```python
class CleanupFileRecord(BaseModel):
    path: str
    bytes: int = 0
    reason: str


class CleanupImageRecord(BaseModel):
    image_id: str
    item_id: str
    path: Optional[str] = None
    reason: str


class CleanupPreview(BaseModel):
    broken_image_records: List[CleanupImageRecord] = Field(default_factory=list)
    unreferenced_files: List[CleanupFileRecord] = Field(default_factory=list)
    total_bytes: int = 0


class CleanupApplyRequest(BaseModel):
    remove_broken_image_records: bool = False
    remove_unreferenced_files: bool = False


class CleanupApplyResult(CleanupPreview):
    removed_broken_image_records: int = 0
    removed_unreferenced_files: int = 0
```

- [ ] **Step 4: Implement cleanup service**

Create `backend/services/library_cleanup.py`:

```python
from __future__ import annotations

from pathlib import Path
from contextlib import suppress

from backend.db import connect
from backend.schemas import CleanupApplyResult, CleanupFileRecord, CleanupImageRecord, CleanupPreview

MEDIA_DIRS = ("originals", "thumbs", "previews")


def _safe_rel_path(library_path: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(library_path.resolve()).as_posix()
    except ValueError:
        return None


def _safe_file(library_path: Path, rel_path: str) -> Path | None:
    candidate = (library_path / rel_path).resolve()
    try:
        candidate.relative_to(library_path.resolve())
    except ValueError:
        return None
    if candidate.is_symlink() or not candidate.is_file():
        return None
    return candidate


def preview_cleanup(library_path: Path | str) -> CleanupPreview:
    library = Path(library_path)
    broken: list[CleanupImageRecord] = []
    referenced: set[str] = set()
    with connect(library) as conn:
        rows = conn.execute("SELECT id,item_id,original_path,thumb_path,preview_path FROM images").fetchall()
    for row in rows:
        paths = [row["original_path"], row["thumb_path"], row["preview_path"]]
        referenced.update(path for path in paths if path)
        missing = [path for path in paths if path and _safe_file(library, path) is None]
        if missing:
            broken.append(CleanupImageRecord(image_id=row["id"], item_id=row["item_id"], path=missing[0], reason="referenced file is missing"))

    unreferenced: list[CleanupFileRecord] = []
    total_bytes = 0
    for dirname in MEDIA_DIRS:
        root = library / dirname
        if not root.is_dir() or root.is_symlink():
            continue
        for candidate in root.rglob("*"):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            rel_path = _safe_rel_path(library, candidate)
            if not rel_path or rel_path in referenced:
                continue
            size = candidate.stat().st_size
            total_bytes += size
            unreferenced.append(CleanupFileRecord(path=rel_path, bytes=size, reason="file is not referenced by any image record"))

    return CleanupPreview(broken_image_records=broken, unreferenced_files=unreferenced, total_bytes=total_bytes)


def apply_cleanup(library_path: Path | str, *, remove_broken_image_records: bool, remove_unreferenced_files: bool) -> CleanupApplyResult:
    library = Path(library_path)
    preview = preview_cleanup(library)
    removed_records = 0
    removed_files = 0
    if remove_broken_image_records and preview.broken_image_records:
        with connect(library) as conn:
            for record in preview.broken_image_records:
                conn.execute("DELETE FROM images WHERE id=?", (record.image_id,))
                removed_records += 1
            conn.commit()
    if remove_unreferenced_files:
        for record in preview.unreferenced_files:
            file_path = _safe_file(library, record.path)
            if not file_path:
                continue
            with suppress(OSError):
                file_path.unlink()
                removed_files += 1
    after = preview_cleanup(library)
    return CleanupApplyResult(
        broken_image_records=after.broken_image_records,
        unreferenced_files=after.unreferenced_files,
        total_bytes=after.total_bytes,
        removed_broken_image_records=removed_records,
        removed_unreferenced_files=removed_files,
    )
```

- [ ] **Step 5: Add cleanup router and register it**

Create `backend/routers/cleanup.py`:

```python
from fastapi import APIRouter, Request

from backend.schemas import CleanupApplyRequest, CleanupApplyResult, CleanupPreview
from backend.services.library_cleanup import apply_cleanup, preview_cleanup

router = APIRouter()


@router.get("/cleanup/preview", response_model=CleanupPreview)
def cleanup_preview(request: Request):
    return preview_cleanup(request.app.state.library_path)


@router.post("/cleanup/apply", response_model=CleanupApplyResult)
def cleanup_apply(request: Request, payload: CleanupApplyRequest):
    return apply_cleanup(
        request.app.state.library_path,
        remove_broken_image_records=payload.remove_broken_image_records,
        remove_unreferenced_files=payload.remove_unreferenced_files,
    )
```

In `backend/main.py`:

- Add `cleanup` to router imports.
- Add:

```python
    app.include_router(cleanup.router, prefix="/api")
```

- [ ] **Step 6: Verify cleanup API**

Run:

```bash
python -m pytest tests/test_cleanup_api.py tests/test_items_api.py::test_patch_favorite_and_delete_item tests/test_media_route_does_not_follow_allowed_dir_symlink_to_database -q
```

Expected: PASS.

- [ ] **Step 7: Commit cleanup API slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add backend/services/library_cleanup.py backend/routers/cleanup.py backend/schemas.py backend/main.py tests/test_cleanup_api.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: add library cleanup preview api"
```

Expected: commit succeeds.

---

### Task 7: Cleanup UI in Config Panel

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Add static cleanup UI test**

Append to `tests/test_frontend_static.py`:

```python
def test_config_panel_has_local_only_cleanup_preview_and_apply():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text()

    assert "CleanupPreview" in types
    assert "cleanupPreview" in api_client
    assert "applyCleanup" in api_client
    assert "cleanupPreview" in config
    assert "loadCleanupPreview" in config
    assert "applyCleanup" in config
    assert "!isDemoMode" in config
    assert "onLibraryCleanup" in config
    assert "onLibraryCleanup={saved}" in app
    assert "cleanup-section" in config
    assert ".cleanup-section" in styles
```

- [ ] **Step 2: Run static test and confirm failure**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_config_panel_has_local_only_cleanup_preview_and_apply -q
```

Expected: FAIL because cleanup UI/client code does not exist.

- [ ] **Step 3: Add frontend cleanup types and API methods**

In `frontend/src/types.ts`, add:

```ts
export interface CleanupFileRecord { path: string; bytes: number; reason: string }
export interface CleanupImageRecord { image_id: string; item_id: string; path?: string | null; reason: string }
export interface CleanupPreview { broken_image_records: CleanupImageRecord[]; unreferenced_files: CleanupFileRecord[]; total_bytes: number }
export interface CleanupApplyRequest { remove_broken_image_records: boolean; remove_unreferenced_files: boolean }
export interface CleanupApplyResult extends CleanupPreview { removed_broken_image_records: number; removed_unreferenced_files: number }
```

In `frontend/src/api/client.ts`:

- Import cleanup types.
- Demo API:

```ts
  cleanupPreview: () => Promise.resolve<CleanupPreview>({ broken_image_records: [], unreferenced_files: [], total_bytes: 0 }),
  applyCleanup: (_payload: CleanupApplyRequest) => demoReadOnly(),
```

- Local API:

```ts
  cleanupPreview: () => json<CleanupPreview>('/api/cleanup/preview'),
  applyCleanup: (payload: CleanupApplyRequest) => json<CleanupApplyResult>('/api/cleanup/apply', { method: 'POST', body: JSON.stringify(payload) }),
```

- [ ] **Step 4: Add cleanup UI to ConfigPanel**

In `frontend/src/components/ConfigPanel.tsx`:

- Import cleanup types.
- Add prop:

```ts
  onLibraryCleanup?: () => void;
```

- Add state:

```ts
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreview>();
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string>();
```

- Add loader:

```ts
  const loadCleanupPreview = useCallback(() => {
    if (isDemoMode) return Promise.resolve(undefined);
    return api.cleanupPreview()
      .then(preview => {
        setCleanupPreview(preview);
        setCleanupMessage(undefined);
        return preview;
      })
      .catch(err => {
        setCleanupMessage(err instanceof Error ? err.message : 'Could not inspect library cleanup.');
        return undefined;
      });
  }, []);
```

- In the `if (open)` effect, call `loadCleanupPreview();`.

- Add apply handler:

```ts
  const applyCleanup = async () => {
    if (!cleanupPreview) return;
    const brokenCount = cleanupPreview.broken_image_records.length;
    const fileCount = cleanupPreview.unreferenced_files.length;
    if (!brokenCount && !fileCount) return;
    if (!confirm(`Clean ${brokenCount} broken image records and ${fileCount} unreferenced files?`)) return;
    setCleanupBusy(true);
    try {
      const result = await api.applyCleanup({ remove_broken_image_records: brokenCount > 0, remove_unreferenced_files: fileCount > 0 });
      setCleanupPreview(result);
      setCleanupMessage(`Removed ${result.removed_broken_image_records} records and ${result.removed_unreferenced_files} files.`);
      onLibraryCleanup?.();
    } catch (err) {
      setCleanupMessage(err instanceof Error ? err.message : 'Cleanup failed.');
    } finally {
      setCleanupBusy(false);
    }
  };
```

- Add section before provider section:

```tsx
      {!isDemoMode && (
        <section className="setting-group cleanup-section">
          <h3>Library cleanup</h3>
          <div className="cleanup-stats" role="status">
            <span>{cleanupPreview?.broken_image_records.length || 0} broken image records</span>
            <span>{cleanupPreview?.unreferenced_files.length || 0} unreferenced files</span>
          </div>
          <div className="provider-actions">
            <button className="secondary" onClick={loadCleanupPreview} disabled={cleanupBusy}>Preview cleanup</button>
            <button className="danger" onClick={applyCleanup} disabled={cleanupBusy || !cleanupPreview || (!cleanupPreview.broken_image_records.length && !cleanupPreview.unreferenced_files.length)}>Apply cleanup</button>
          </div>
          {cleanupMessage && <p className="provider-message">{cleanupMessage}</p>}
        </section>
      )}
```

- [ ] **Step 5: Wire App callback and styles**

In `frontend/src/App.tsx`, pass:

```tsx
onLibraryCleanup={saved}
```

to `ConfigPanel`.

In `frontend/src/styles.css`, add:

```css
.cleanup-section .provider-actions{margin-top:10px}.cleanup-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.cleanup-stats span{border:1px solid rgba(33,25,34,.10);border-radius:10px;padding:10px;background:rgba(255,255,255,.72);font-size:12px;font-weight:850}
```

- [ ] **Step 6: Verify cleanup UI**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_config_panel_has_local_only_cleanup_preview_and_apply -q
npm run build
```

Expected: both PASS.

- [ ] **Step 7: Commit cleanup UI slice**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add frontend/src/types.ts frontend/src/api/client.ts frontend/src/components/ConfigPanel.tsx frontend/src/App.tsx frontend/src/styles.css tests/test_frontend_static.py
git -c safe.directory=G:/Codex/image-prompt-library commit -m "feat: add cleanup controls"
```

Expected: commit succeeds.

---

### Task 8: Final Regression and Release Notes

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS.md`
- Test: existing suite and frontend build

- [ ] **Step 1: Update user-facing docs**

In `README.md`, add a concise section under library usage/search features:

```markdown
Power-user library management:

- Use the visible sort control to order references by updated date, created date, title, source, or model.
- Mix search keywords with lightweight filters such as `created:7d apple`, `tag:template`, `collection:Packaging`, `source:awesome`, `fav:true`, or `has:reference`.
- In local installs, use selection mode to archive, favorite, tag, move, or delete multiple references.
- In local Config, preview cleanup before removing broken image records or unreferenced local media files.
```

In `docs/PROJECT_STATUS.md`, add a short dated note near the current status section:

```markdown
Library Power-User Polish adds visible sort controls, lightweight structured search filters, backend-backed batch management, and preview-first local cleanup for broken image records and unreferenced media files.
```

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
python -m pytest tests/test_search_query.py tests/test_items_api.py tests/test_cleanup_api.py tests/test_image_store.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend static tests and build**

Run:

```bash
python -m pytest tests/test_frontend_static.py tests/test_github_pages_demo.py -q
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run public/demo docs tests**

Run:

```bash
python -m pytest tests/test_public_mvp.py tests/test_public_ci_release.py -q
```

Expected: PASS.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library status --short
git -c safe.directory=G:/Codex/image-prompt-library diff --stat
```

Expected: only files tied to Library Power-User Polish are changed.

- [ ] **Step 6: Commit final docs/checkpoint**

Run:

```bash
git -c safe.directory=G:/Codex/image-prompt-library add README.md docs/PROJECT_STATUS.md
git -c safe.directory=G:/Codex/image-prompt-library commit -m "docs: document library power-user polish"
```

Expected: commit succeeds if docs changed. If docs were already updated in a previous slice, there may be nothing to commit.

---

## Self-Review Checklist

Spec coverage:

- Search/filter clarity: Tasks 1, 2, and 3.
- Visible sort control: Task 3.
- Active state chips: Task 3.
- Batch management: Tasks 4 and 5.
- Cleanup preview/apply: Tasks 6 and 7.
- Archive/delete confidence: Tasks 4 and 5, plus existing delete confirmation preserved.
- Provenance preservation: Tasks 4 and 6 use existing item update/delete paths and do not alter provenance fields.
- Demo read-only behavior: Tasks 3, 5, and 7 keep mutation methods read-only in demo API.

Implementation decisions:

- Structured filter chips are display-only in the first implementation; clearing the search input clears them.
- Cleanup lives inside the existing Config drawer to avoid a new management surface.
- Generation staging cleanup is deferred unless Task 6 finds a traceable database reason during implementation.

No new dependencies are required.
