# Task 3 Report: Frontend Provider And Settings Hardening

## Scope

Implemented Task 3 on branch `codex/generation-hardening` from `G:\Codex\image-prompt-library`.

Task-owned changes only:

- `frontend/src/App.tsx`
- `frontend/src/components/GenerationPanel.tsx`
- `frontend/src/styles.css`
- `tests/test_frontend_static.py`

I did not touch backend stale-timeout logic from Task 2.

## TDD Evidence

### 1. RED: add the required static test first

Added:

- `test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit`

Initial targeted run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit -q
```

First failure encountered:

- `UnicodeDecodeError: 'cp950' codec can't decode byte 0xc3 ...`

This happened before the intended assertion because this Windows shell defaults to `cp950` while the frontend files are UTF-8. I updated only the new test's `read_text(...)` calls to use `encoding="utf-8"` so the test could fail for the requested behavior gap instead of locale noise.

Re-run after that adjustment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit -q
```

Observed expected RED failure:

- `assert "provider.can_generate ??" in app`

### 2. GREEN: implement the smallest code to satisfy the brief

Implemented:

- `App.tsx`
  - Hardened `generationProviderConnected(provider)` to use `provider.can_generate ?? Boolean(provider.available && provider.authenticated && provider.configured)`.

- `GenerationPanel.tsx`
  - Added `providerCanGenerate(provider?)`
  - Added `providerReadinessLabel(provider?)`
  - Derived:
    - `selectedProviderCanGenerate`
    - `selectedProviderMessage`
  - Blocked `createJob()` when the selected provider cannot generate.
  - Disabled the primary Generate button when provider readiness is false.
  - Rendered provider readiness copy inside `.generation-compact-controls` before the primary action.

- `styles.css`
  - Added `.generation-provider-readiness`
  - Added `.generation-provider-readiness.is-ready`
  - Added `.generation-provider-readiness.needs-attention`
  - Added mobile wrapping rule inside the existing generation-controls media block.

### 3. VERIFY GREEN

Targeted static test:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit -q
```

Result:

- `1 passed, 1 warning in 0.42s`

Warning:

- `PytestCacheWarning` for `.pytest_cache` permission write; this did not affect test assertions.

## Build Verification

Ran:

```powershell
npm run build
```

Result:

- `tsc && vite build` succeeded
- Production bundle emitted successfully under `frontend/dist`

## Files Changed

### `frontend/src/App.tsx`

- Updated generation availability helper to honor additive readiness field `can_generate`.

### `frontend/src/components/GenerationPanel.tsx`

- Added provider readiness helpers and UI copy.
- Prevented submit when the selected provider is not generation-ready.
- Kept model, quality, aspect, and attachment controls visible before submit.

### `frontend/src/styles.css`

- Added minimal readiness styling and mobile wrapping behavior.

### `tests/test_frontend_static.py`

- Added the required static regression test.
- Used explicit UTF-8 reads in the new test to avoid locale-dependent failures on this machine.

## Self-Review

Checked against the brief:

- Existing `GenerationPanel` / `GenerationQueueDrawer` structure preserved.
- No advanced settings added.
- No new provider architecture introduced.
- No backend/provider settings exposure expanded.
- Submit is blocked for unavailable selected providers.
- Readiness copy is visible in `GenerationPanel`.
- Existing compact controls remain visible.

## Risks / Notes

- The new static test uses explicit UTF-8 decoding because the local Windows default codec is not UTF-8. Without that, the test fails before reaching the intended readiness assertions.
- `generationProviderConnected()` now honors `can_generate` for all providers, including `manual_upload` when present from backend/demo data. That matches the additive readiness contract described in Tasks 1 and 3.

## Commit

Planned commit message:

```text
feat: clarify generation provider readiness in UI
```

## Review Fixes

### Follow-up findings addressed

1. `GenerationPanel` initial provider auto-selection now uses additive readiness via `providerCanGenerate(...)` for both the preferred non-manual provider and the fallback provider search.
2. The compact controls grid now matches the seven rendered items:
   - desktop: `44px 44px 44px 44px minmax(0,1fr) minmax(112px,max-content) 44px`
   - mobile: `40px 40px 40px 40px 40px minmax(88px,1fr) 40px`
   - mobile readiness copy now wraps with `grid-column: 1 / span 5` instead of the ineffective old `flex` rule on a grid item.
3. Static coverage now asserts:
   - initial auto-selection uses `providerCanGenerate(...)`
   - fallback selection uses `nextProviders.find(providerCanGenerate)`
   - desktop/mobile compact grid layouts reflect the seven-item row
   - the old mobile readiness `flex` rule is absent

### Focused verification rerun

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit -q
```

Result:

- `1 passed, 1 warning in 0.47s`
- warning remained the same `PytestCacheWarning` for `.pytest_cache` permission writes

### Build rerun

```powershell
npm run build
```

Result:

- `tsc && vite build` succeeded
- frontend production bundle emitted under `frontend/dist`
