# Windows Stable Discovery Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the native Windows installer discover compatible stable releases correctly under Windows PowerShell 5.1.

**Architecture:** Preserve the existing GitHub release and manifest validation flow. Store the API response in a variable before the language `foreach` statement so PowerShell 5.1 enumerates each release instead of treating the `ConvertFrom-Json` array as one candidate.

**Tech Stack:** Windows PowerShell 5.1, Python 3.11, pytest.

## Global Constraints

- Do not change explicit `-Version` release selection.
- Do not weaken manifest, asset-origin, or checksum validation.
- Add no dependencies or new abstractions.

---

### Task 1: Fix stable release enumeration

**Files:**
- Modify: `scripts/install.ps1`
- Test: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: `Get-ApiJson -Uri <releases-url>` returning the PowerShell 5.1 `ConvertFrom-Json` result.
- Produces: `Resolve-Release` returning the first stable candidate accepted by `Test-ApiReleaseCompatibility`.

- [x] **Step 1: Write the failing behavioral test**

Stub `Get-ApiJson` with a JSON array containing one incompatible stable release followed by one compatible stable release. Override `Test-ApiReleaseCompatibility` so only the second tag passes, then assert `Resolve-Release` returns that tag.

- [x] **Step 2: Verify the regression test fails**

Run: `python -m pytest -q tests/test_windows_installer.py::test_windows_installer_enumerates_stable_api_releases_in_powershell_51`

Expected: failure with `No published stable release currently supports native Windows PowerShell installation.`

- [x] **Step 3: Apply the minimal fix**

```powershell
$candidates = Get-ApiJson -Uri "$apiBase`?per_page=20"
foreach ($candidate in $candidates) {
```

- [x] **Step 4: Verify the focused Windows installer tests**

Run the regression test, then `python -m pytest -q tests/test_windows_installer.py`.

Expected: all selected tests pass.

- [ ] **Step 5: Publish and release-gate the hotfix**

Commit only the plan, installer, and regression test; open a PR; merge after CI succeeds. Re-run a raw-main Windows install without `-Version`, verify it selects `v0.8.0`, then cleanly uninstall before promoting `v0.8.0` to stable/latest again.
