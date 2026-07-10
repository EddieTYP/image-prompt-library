# Task 4 Report: First-Run Docs Cleanup

## Scope

Implemented Task 4 on branch `codex/install-onboarding-polish` from `G:\Codex\image-prompt-library`.

Changed only task-allowed files:

- `README.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`
- `ROADMAP.md`
- `tests/test_public_mvp.py`
- `tests/test_installer_release.py`
- `.superpowers/sdd/task-4-report.md`

## Changes

- Added docs assertions for first-run status/doctor guidance, `v0.7.7-beta`, empty fresh libraries, platform wording, and `sample-data en`.
- Updated README quick start with fresh empty-library guidance, a compact `sample-data en` command, and quick `status` / `doctor` checks.
- Added `## First run` to the installation guide after latest-release install instructions.
- Expanded installation health checks to include `image-prompt-library status` and `image-prompt-library doctor`.
- Updated troubleshooting empty-library guidance with `+ Add`, `sample-data en`, `status`, and `doctor`.
- Updated ROADMAP current release to `v0.7.7-beta` and moved near-term priority language toward install/onboarding polish.

## TDD Evidence

Added tests first, then ran the requested focused checks before docs edits.

Expected RED result:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -m pytest tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers -q
```

Result:

- `2 failed, 3 warnings`
- Failures were for missing `v0.7.7-beta` in `ROADMAP.md` and missing `image-prompt-library status` in `README.md`.

## Verification

Re-ran the same focused checks after the docs updates:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -m pytest tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers -q
```

Result:

- `2 passed, 2 warnings in 0.70s`

Warnings:

- `StarletteDeprecationWarning` from `fastapi.testclient` importing Starlette `TestClient`.
- `PytestCacheWarning` because pytest could not write `.pytest_cache\v\cache\nodeids` due to permission denied.
