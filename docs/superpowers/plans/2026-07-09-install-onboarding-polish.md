# Install and Onboarding Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the first successful local-install experience with contextual first-run UI, a compact Config setup summary, clearer CLI diagnostics, and updated first-run docs.

**Architecture:** Reuse existing frontend state and API calls rather than adding backend schema or endpoints. `App.tsx` decides whether an empty list is a true first-run local empty library, `CardsView.tsx` renders the appropriate empty state, `ConfigPanel.tsx` summarizes existing config/update/provider data, and `scripts/appctl.sh` keeps CLI diagnostics local and direct.

**Tech Stack:** React + TypeScript frontend, existing CSS, Bash installer/runtime scripts, Python subprocess/static tests, FastAPI existing endpoints.

## Global Constraints

- No installer architecture rewrite.
- No native Windows PowerShell installer.
- No Docker Compose path.
- No account system.
- No import or external-inspiration work.
- No generation provider behavior changes beyond clearer onboarding links.
- No automatic sample-data install.
- No forced onboarding wizard.
- No new dependencies.
- Preserve GitHub Pages demo as read-only.
- Use existing visual language and component patterns.
- Keep mobile layouts touch-friendly and avoid horizontal overflow.

---

## File Structure

- Modify `frontend/src/App.tsx`: compute first-run empty-library state and pass Config opener into Cards view.
- Modify `frontend/src/components/CardsView.tsx`: render first-run panel separately from normal no-results.
- Modify `frontend/src/components/ConfigPanel.tsx`: add Local Setup section using existing config, update, and provider state.
- Modify `frontend/src/utils/i18n.ts`: add concise labels for onboarding/setup copy.
- Modify `frontend/src/styles.css`: style the first-run panel and Local Setup section using existing empty/settings patterns.
- Modify `scripts/appctl.sh`: polish `doctor` output and add `status`.
- Modify `tests/test_frontend_static.py`: add static contract tests for first-run UI and setup summary.
- Modify `tests/test_installer_release.py`: add/adjust installer CLI contract and subprocess tests for doctor/status.
- Modify `tests/test_public_mvp.py`: assert first-run/status docs are public-safe.
- Modify `README.md`, `docs/INSTALLATION.md`, `docs/TROUBLESHOOTING.md`, `ROADMAP.md`: update first-run, status, doctor, and current version wording.

---

### Task 1: First-Run Empty Library UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/CardsView.tsx`
- Modify: `frontend/src/utils/i18n.ts`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Produces: `CardsView` props `emptyMode?: 'first-run' | 'no-results'` and `onOpenConfig?: () => void`.
- Consumes: existing `isDemoMode`, `q`, `clusterId`, `localizedData.items`, `openNewItemEditor`, and `setConfigOpen(true)`.

- [ ] **Step 1: Write failing static tests for first-run vs no-results behavior**

Add this test near the existing CardsView/App tests in `tests/test_frontend_static.py`:

```python
def test_local_empty_library_uses_first_run_panel_without_replacing_search_no_results():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()

    assert "const emptyMode = !isDemoMode && localizedData.items.length === 0 && !q.trim() && !clusterId ? 'first-run' : 'no-results'" in app
    assert "emptyMode={emptyMode}" in app
    assert "onOpenConfig={() => setConfigOpen(true)}" in app
    assert "emptyMode?: 'first-run' | 'no-results'" in cards
    assert "emptyMode === 'first-run'" in cards
    assert "t('firstRunEmptyTitle')" in cards
    assert "t('firstRunSampleCommand')" in cards
    assert "onOpenConfig" in cards
    assert "t('noMatchingPrompts')" in cards
    assert "firstRunEmptyTitle" in i18n
    assert "Your private library is empty" in i18n
    assert "image-prompt-library sample-data en" in i18n
    assert ".first-run-empty" in css
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_local_empty_library_uses_first_run_panel_without_replacing_search_no_results -q
```

Expected: FAIL because the first-run strings/props do not exist.

- [ ] **Step 3: Add first-run translation keys**

In `frontend/src/utils/i18n.ts`, extend `TranslationKey` with:

```ts
  | 'firstRunEmptyTitle' | 'firstRunEmptyHelp' | 'firstRunOpenConfig'
  | 'firstRunSampleCommand' | 'firstRunSampleHelp' | 'firstRunGenerationHelp';
```

Add English translations:

```ts
    firstRunEmptyTitle: 'Your private library is empty',
    firstRunEmptyHelp: 'That is expected after a fresh local install. Add a prompt, import optional samples, or connect generation when you are ready.',
    firstRunOpenConfig: 'Open Config',
    firstRunSampleCommand: 'image-prompt-library sample-data en',
    firstRunSampleHelp: 'Optional: run this command in Terminal to add starter references.',
    firstRunGenerationHelp: 'Optional generation lives in Config and requires ChatGPT / Codex OAuth.',
```

Add Traditional Chinese translations:

```ts
    firstRunEmptyTitle: '你的私人 library 仍然是空的',
    firstRunEmptyHelp: '新安裝後這是正常的。你可以新增 prompt、安裝 sample data，或之後再連接 generation。',
    firstRunOpenConfig: '開啟 Config',
    firstRunSampleCommand: 'image-prompt-library sample-data en',
    firstRunSampleHelp: '可選：在 Terminal 執行這個指令加入 starter references。',
    firstRunGenerationHelp: '可選 generation 在 Config 裏，需要 ChatGPT / Codex OAuth。',
```

Add Simplified Chinese translations:

```ts
    firstRunEmptyTitle: '你的私人 library 还是空的',
    firstRunEmptyHelp: '新安装后这是正常的。你可以新增 prompt、安装 sample data，或之后再连接 generation。',
    firstRunOpenConfig: '打开 Config',
    firstRunSampleCommand: 'image-prompt-library sample-data en',
    firstRunSampleHelp: '可选：在 Terminal 执行这个命令加入 starter references。',
    firstRunGenerationHelp: '可选 generation 在 Config 里，需要 ChatGPT / Codex OAuth。',
```

- [ ] **Step 4: Pass empty mode and Config opener from App**

In `frontend/src/App.tsx`, add this near other derived UI constants before `return`:

```ts
  const emptyMode = !isDemoMode && localizedData.items.length === 0 && !q.trim() && !clusterId ? 'first-run' : 'no-results';
```

Update the CardsView call:

```tsx
        : <CardsView t={t} items={localizedData.items} emptyMode={emptyMode} onOpen={setDetailId} onFavorite={isDemoMode ? undefined : favorite} onEdit={isDemoMode ? undefined : editSummary} onToggleSelection={selectionMode ? toggleSelectedItem : undefined} selectedIds={selectedItemIds} onCopyPrompt={copyPrompt} onAdd={isDemoMode ? undefined : openNewItemEditor} onOpenConfig={() => setConfigOpen(true)} />}
```

- [ ] **Step 5: Render first-run panel in CardsView**

Update `frontend/src/components/CardsView.tsx` props:

```ts
  emptyMode,
  onOpenConfig,
}: {
  items: ItemSummary[];
  emptyMode?: 'first-run' | 'no-results';
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  onToggleSelection?: (id: string) => void;
  selectedIds?: Set<string>;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd?: () => void;
  onOpenConfig?: () => void;
}) {
```

Replace the empty block with:

```tsx
  if (!items.length && emptyMode === 'first-run') {
    return (
      <div className="empty first-run-empty">
        <p className="empty-eyebrow">Local install</p>
        <h2>{t('firstRunEmptyTitle')}</h2>
        <p>{t('firstRunEmptyHelp')}</p>
        <div className="empty-actions">
          {onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
          {onOpenConfig && <button className="secondary" onClick={onOpenConfig}>{t('firstRunOpenConfig')}</button>}
        </div>
        <div className="first-run-command">
          <span>{t('firstRunSampleHelp')}</span>
          <code>{t('firstRunSampleCommand')}</code>
        </div>
        <p className="first-run-generation-hint">{t('firstRunGenerationHelp')}</p>
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="empty">
        <h2>{t('noMatchingPrompts')}</h2>
        <p>{t('noMatchingPromptsHelp')}</p>
        <div className="empty-actions">
          {onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
        </div>
      </div>
    );
  }
```

- [ ] **Step 6: Add minimal CSS**

In `frontend/src/styles.css`, extend the existing `.empty` area:

```css
.first-run-empty{text-align:left}
.empty-eyebrow{margin:0 0 8px;color:var(--accent-strong)!important;font-size:12px;text-transform:uppercase;letter-spacing:.08em;font-weight:950}
.first-run-empty .empty-actions{justify-content:flex-start}
.first-run-command{margin-top:18px;border:1px dashed #d8d1c3;border-radius:16px;background:#fffaf0;padding:12px;display:grid;gap:7px;color:var(--muted);font-size:13px}
.first-run-command code{display:block;width:100%;overflow:auto;border-radius:12px;background:#211922;color:#fff;padding:10px;font-size:12px}
.first-run-generation-hint{margin-top:12px!important;font-size:13px}
```

- [ ] **Step 7: Run focused frontend static test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_local_empty_library_uses_first_run_panel_without_replacing_search_no_results -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add frontend/src/App.tsx frontend/src/components/CardsView.tsx frontend/src/utils/i18n.ts frontend/src/styles.css tests/test_frontend_static.py
git commit -m "feat: add first-run empty library panel"
```

---

### Task 2: Config Local Setup Summary

**Files:**
- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `frontend/src/utils/i18n.ts`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes: existing `cfg`, `providers`, `updateStatus`, `providerStateLabel()`, and `providerCanGenerate` equivalent inline logic.
- Produces: a `.local-setup-section` in Config with command hints.

- [ ] **Step 1: Write failing static test**

Add to `tests/test_frontend_static.py`:

```python
def test_config_panel_has_local_setup_summary_for_installed_users():
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()

    assert "local-setup-section" in config
    assert "t('localSetup')" in config
    assert "cfg?.version" in config
    assert "cfg?.library_path" in config
    assert "cfg?.database_path" in config
    assert "updateStatus?.current_version" in config
    assert "readyProviderCount" in config
    assert "image-prompt-library status" in config
    assert "image-prompt-library doctor" in config
    assert "image-prompt-library sample-data en" in config
    assert "localSetup" in i18n
    assert "Local setup" in i18n
    assert ".local-setup-section" in css
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_config_panel_has_local_setup_summary_for_installed_users -q
```

Expected: FAIL because the setup section does not exist.

- [ ] **Step 3: Add translation keys**

Extend `TranslationKey`:

```ts
  | 'localSetup' | 'localSetupHelp' | 'appVersion' | 'updateStatusLabel'
  | 'generationStatusLabel' | 'setupCommands' | 'statusCommandHelp' | 'doctorCommandHelp';
```

Add English translations:

```ts
    localSetup: 'Local setup',
    localSetupHelp: 'Quick checks for this installed local app.',
    appVersion: 'App version',
    updateStatusLabel: 'Update status',
    generationStatusLabel: 'Generation status',
    setupCommands: 'Setup commands',
    statusCommandHelp: 'Quick local summary',
    doctorCommandHelp: 'Detailed diagnostics',
```

Add Traditional Chinese:

```ts
    localSetup: '本機設定',
    localSetupHelp: '快速檢查這個本機安裝。',
    appVersion: 'App 版本',
    updateStatusLabel: '更新狀態',
    generationStatusLabel: 'Generation 狀態',
    setupCommands: '設定指令',
    statusCommandHelp: '快速本機摘要',
    doctorCommandHelp: '詳細診斷',
```

Add Simplified Chinese:

```ts
    localSetup: '本机设置',
    localSetupHelp: '快速检查这个本机安装。',
    appVersion: 'App 版本',
    updateStatusLabel: '更新状态',
    generationStatusLabel: 'Generation 状态',
    setupCommands: '设置命令',
    statusCommandHelp: '快速本机摘要',
    doctorCommandHelp: '详细诊断',
```

- [ ] **Step 4: Add provider readiness summary**

In `ConfigPanel.tsx`, after `activeUpdateJobs`:

```ts
  const readyProviderCount = providers.filter(provider => provider.can_generate ?? Boolean(provider.available && provider.authenticated && provider.configured)).length;
  const generationSetupLabel = readyProviderCount > 0 ? `${readyProviderCount} ready` : 'Optional; not connected';
  const updateSetupLabel = updateStatus
    ? (updateStatus.update_available ? `Update available: ${updateStatus.latest_version}` : `Up to date: ${updateStatus.current_version}`)
    : 'Unavailable';
```

- [ ] **Step 5: Render Local Setup near top of Config**

In `ConfigPanel.tsx`, after the drawer head and before UI language:

```tsx
      {!isDemoMode && (
        <section className="setting-group local-setup-section">
          <h3>{t('localSetup')}</h3>
          <p className="muted">{t('localSetupHelp')}</p>
          <dl className="local-setup-list">
            <div><dt>{t('appVersion')}</dt><dd><code>{cfg?.version || updateStatus?.current_version || 'unknown'}</code></dd></div>
            <div><dt>{t('libraryPath')}</dt><dd><code>{cfg?.library_path || 'unavailable'}</code></dd></div>
            <div><dt>{t('databasePath')}</dt><dd><code>{cfg?.database_path || 'unavailable'}</code></dd></div>
            <div><dt>{t('updateStatusLabel')}</dt><dd>{updateSetupLabel}</dd></div>
            <div><dt>{t('generationStatusLabel')}</dt><dd>{generationSetupLabel}</dd></div>
          </dl>
          <div className="local-setup-commands" aria-label={t('setupCommands')}>
            <p><span>{t('statusCommandHelp')}</span><code>image-prompt-library status</code></p>
            <p><span>{t('doctorCommandHelp')}</span><code>image-prompt-library doctor</code></p>
            <p><span>{t('firstRunSampleHelp')}</span><code>image-prompt-library sample-data en</code></p>
          </div>
        </section>
      )}
```

- [ ] **Step 6: Add CSS for setup summary**

Add to `frontend/src/styles.css` near Config styles:

```css
.local-setup-section{background:#fff}
.local-setup-list{display:grid;gap:8px;margin:0}
.local-setup-list div{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px;align-items:start}
.local-setup-list dt{color:#756d61;font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:.04em}
.local-setup-list dd{margin:0;min-width:0;color:#332b25;font-size:13px;font-weight:800;overflow-wrap:anywhere}
.local-setup-list code,.local-setup-commands code{font-size:11px}
.local-setup-commands{display:grid;gap:8px;margin-top:12px}
.local-setup-commands p{margin:0;display:grid;gap:4px}
.local-setup-commands span{font-size:12px;color:var(--muted)}
```

- [ ] **Step 7: Run focused test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py::test_config_panel_has_local_setup_summary_for_installed_users -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add frontend/src/components/ConfigPanel.tsx frontend/src/utils/i18n.ts frontend/src/styles.css tests/test_frontend_static.py
git commit -m "feat: show local setup summary"
```

---

### Task 3: CLI Doctor Polish and Status Command

**Files:**
- Modify: `scripts/appctl.sh`
- Test: `tests/test_installer_release.py`

**Interfaces:**
- Produces: `image-prompt-library status` command.
- Keeps: `image-prompt-library doctor` command and existing sensitive-value guarantees.

- [ ] **Step 1: Write failing script contract assertions**

In `test_installer_and_runtime_scripts_define_versioned_install_contract`, add:

```python
    assert "status)" in appctl
    assert "status_app()" in appctl
    assert "Image Prompt Library status" in appctl
    assert "## App" in appctl
    assert "## Next steps" in appctl
```

- [ ] **Step 2: Update doctor subprocess test expectations**

In `test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values`, replace the current output assertions after returncode with:

```python
    assert "Image Prompt Library doctor" in doctor.stdout
    assert "## App" in doctor.stdout
    assert "OK Version: v9.9.2-test" in doctor.stdout
    assert f"OK Install prefix: {prefix}" in doctor.stdout
    assert f"OK Library path: {library}" in doctor.stdout
    assert "OK Backend URL: http://127.0.0.1:8000/" in doctor.stdout
    assert "## Database" in doctor.stdout
    assert "OK Database integrity: ok" in doctor.stdout
    assert "Item count: 0" in doctor.stdout
    assert "## Generation" in doctor.stdout
    assert "openai_codex_oauth_native" in doctor.stdout
    assert "## Next steps" in doctor.stdout
    assert "image-prompt-library sample-data en" in doctor.stdout
    assert "[REDACTED]" not in doctor.stdout
    assert "app_" not in doctor.stdout
```

- [ ] **Step 3: Add status subprocess test**

Add after the doctor test:

```python
def test_installed_status_reports_short_local_summary(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.3-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = sys.executable
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.3-test",
            "--prefix",
            str(prefix),
            "--library-path",
            str(library),
            "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"
    status = subprocess.run(
        ["bash", str(appctl), "status"],
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix)},
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert status.returncode == 0, status.stdout + status.stderr
    assert "Image Prompt Library status" in status.stdout
    assert "Version: v9.9.3-test" in status.stdout
    assert f"Library: {library}" in status.stdout
    assert "URL: http://127.0.0.1:8000/" in status.stdout
    assert "Items: 0" in status.stdout
    assert "Generation:" in status.stdout
    assert "Run image-prompt-library doctor for detailed diagnostics." in status.stdout
    assert "[REDACTED]" not in status.stdout
    assert "app_" not in status.stdout
```

- [ ] **Step 4: Run failing installer tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract tests/test_installer_release.py::test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values tests/test_installer_release.py::test_installed_status_reports_short_local_summary -q
```

Expected: FAIL.

- [ ] **Step 5: Replace doctor print body with headed output**

In the Python heredoc inside `doctor_app()`, keep existing imports and variables, then change the print section to this shape:

```python
print("Image Prompt Library doctor")
print()
print("## App")
print(f"OK Version: {version}")
print(f"OK Install prefix: {app_prefix}")
print(f"OK App root: {app_root}")
print(f"OK Backend URL: http://{backend_host}:{backend_port}/")
print(f"OK Platform: {platform.system()} {platform.release()}")
print()
print("## Library")
print(f"OK Library path: {library_path}")
```

Update the database block to print:

```python
    print()
    print("## Database")
    print(f"OK Database path: {db_path}")
    print(f"OK Database integrity: {integrity}")
    print(f"OK Item count: {item_count}")
```

On exception:

```python
    print()
    print("## Database")
    print(f"ERROR Database integrity: {type(exc).__name__}")
    item_count = None
```

Update generation output to print a headed section:

```python
print()
print("## Generation")
...
print(f"{severity} Generation provider: {PROVIDER_ID} state={state} configured={configured}")
```

Use `severity = "OK" if state == "saved_auth_present" else "WARN"`.

Update service output under:

```python
print()
print("## Updates / Service")
```

Add final next steps:

```python
print()
print("## Next steps")
if item_count == 0:
    print("WARN Empty library: add a prompt in the app, or run image-prompt-library sample-data en")
else:
    print("OK Library has saved references.")
if generation_optional:
    print("OK Generation is optional. Connect ChatGPT / Codex OAuth in Config only if you want local generation.")
print("OK For a shorter summary, run image-prompt-library status")
```

Define `generation_optional = True` before generation try block.

- [ ] **Step 6: Add status_app()**

Add this Bash function after `doctor_app()`:

```bash
status_app() {
  load_env
  PYTHON_BIN="$(python_bin)"
  cd "$APP_ROOT"
  "$PYTHON_BIN" - "$APP_ROOT" "$IMAGE_PROMPT_LIBRARY_PATH" "$BACKEND_HOST" "$BACKEND_PORT" "$(print_version)" <<'PY'
from __future__ import annotations

import platform
import sqlite3
import sys
from pathlib import Path

app_root = Path(sys.argv[1])
library_path = Path(sys.argv[2]).expanduser()
backend_host = sys.argv[3]
backend_port = sys.argv[4]
version = sys.argv[5]
sys.path.insert(0, str(app_root))

print("Image Prompt Library status")
print(f"Version: {version}")
print(f"Library: {library_path}")
print(f"URL: http://{backend_host}:{backend_port}/")

try:
    db_path = library_path / "db.sqlite"
    if not db_path.exists():
        from backend.db import init_db
        init_db(library_path)
    with sqlite3.connect(db_path) as conn:
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Items: {item_count}")
except Exception as exc:
    print(f"Items: unavailable ({type(exc).__name__})")

try:
    from backend.services.openai_codex_native import CodexNativeAuthStore, PROVIDER_ID, configured_client_id
    store = CodexNativeAuthStore()
    configured = bool(configured_client_id())
    saved_auth_present = store.path.is_file()
    if not configured:
        state = "not configured"
    elif saved_auth_present:
        state = "connected"
    else:
        state = "not connected"
    print(f"Generation: {PROVIDER_ID} {state}")
except Exception as exc:
    print(f"Generation: unavailable ({type(exc).__name__})")

if platform.system() == "Darwin":
    print("Service: macOS launchd available; run image-prompt-library service status for details.")
else:
    print("Service: not applicable")

print("Run image-prompt-library doctor for detailed diagnostics.")
PY
}
```

- [ ] **Step 7: Wire status into usage and command dispatch**

In `usage()` add:

```text
  status                Print short local app status
```

In the command case add:

```bash
  status) status_app "$@" ;;
```

- [ ] **Step 8: Run focused installer tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract tests/test_installer_release.py::test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values tests/test_installer_release.py::test_installed_status_reports_short_local_summary -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

Run:

```bash
git add scripts/appctl.sh tests/test_installer_release.py
git commit -m "feat: polish local diagnostics commands"
```

---

### Task 4: First-Run Docs Cleanup

**Files:**
- Modify: `README.md`
- Modify: `docs/INSTALLATION.md`
- Modify: `docs/TROUBLESHOOTING.md`
- Modify: `ROADMAP.md`
- Test: `tests/test_public_mvp.py`
- Test: `tests/test_installer_release.py`

**Interfaces:**
- Consumes: CLI command names from Task 3: `image-prompt-library status`, `image-prompt-library doctor`.
- Produces: public-safe docs describing first-run and diagnostics.

- [ ] **Step 1: Write failing docs tests**

Add to `tests/test_public_mvp.py`:

```python
def test_public_docs_explain_first_run_status_and_doctor():
    readme = (ROOT / "README.md").read_text()
    installation = (ROOT / "docs" / "INSTALLATION.md").read_text()
    troubleshooting = (ROOT / "docs" / "TROUBLESHOOTING.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()

    assert "v0.7.7-beta" in roadmap
    assert "image-prompt-library status" in readme
    assert "image-prompt-library doctor" in readme
    assert "A fresh local library starts empty" in readme
    assert "image-prompt-library status" in installation
    assert "image-prompt-library doctor" in installation
    assert "First run" in installation
    assert "image-prompt-library status" in troubleshooting
    assert "image-prompt-library doctor" in troubleshooting
    assert "sample-data en" in troubleshooting
    assert "Native Windows PowerShell" in installation
    assert "WSL 2" in installation
```

In `tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers`, add:

```python
    assert "image-prompt-library status" in readme
    assert "image-prompt-library status" in installation
```

- [ ] **Step 2: Run failing docs tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers -q
```

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update README Quick Start**

In `README.md`, after the start instructions, add:

```markdown
A fresh local library starts empty. From there you can add your first prompt in the app, or import optional starter references:

```bash
image-prompt-library sample-data en
```

For a quick local check:

```bash
image-prompt-library status
image-prompt-library doctor
```
```

Keep the existing sample-data language commands below; do not duplicate the full explanation twice.

- [ ] **Step 4: Update Installation guide**

In `docs/INSTALLATION.md`, add a `## First run` section after install:

```markdown
## First run

A fresh local library starts empty. Open the local URL, add your first prompt, or import optional starter references:

```bash
image-prompt-library sample-data en
```

Check the installed app at any time:

```bash
image-prompt-library status
image-prompt-library doctor
```
```

In Health check, include:

```markdown
Use `status` for a short summary and `doctor` for detailed diagnostics:

```bash
image-prompt-library status
image-prompt-library doctor
```
```

- [ ] **Step 5: Update Troubleshooting**

In `docs/TROUBLESHOOTING.md`, update “Empty library after first start”:

```markdown
That is expected for a fresh install. Click `+ Add` to create your first prompt card, or install optional starter references:

```bash
image-prompt-library sample-data en
```

If you are unsure which library folder the app is using, run:

```bash
image-prompt-library status
image-prompt-library doctor
```
```

- [ ] **Step 6: Update Roadmap current version**

In `ROADMAP.md`, change:

```markdown
The current release is `v0.7.5-beta`.
```

to:

```markdown
The current release is `v0.7.7-beta`.
```

Also update near-term priorities by replacing completed search/generation hardening language with install/onboarding polish:

```markdown
- Polish first-run install/onboarding guidance, including empty-library guidance and local diagnostics.
```

- [ ] **Step 7: Run focused docs tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

Run:

```bash
git add README.md docs/INSTALLATION.md docs/TROUBLESHOOTING.md ROADMAP.md tests/test_public_mvp.py tests/test_installer_release.py
git commit -m "docs: clarify first-run local setup"
```

---

### Task 5: Integrated Verification and Visual QA

**Files:**
- Create: `docs/qa/2026-07-09-install-onboarding-polish-qa.md`

**Interfaces:**
- Consumes all prior tasks.
- Produces QA evidence for implementation completion.

- [ ] **Step 1: Run focused automated tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract tests/test_installer_release.py::test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values tests/test_installer_release.py::test_installed_status_reports_short_local_summary tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 3: Run local app with an empty temporary library**

Use a fresh temporary library path and a non-default port. Start the server in a background terminal/session:

```bash
$env:IMAGE_PROMPT_LIBRARY_PATH="$env:TEMP\\ipl-onboarding-empty-library"
$env:BACKEND_PORT="8001"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Expected: server starts and `http://127.0.0.1:8001/` loads.

- [ ] **Step 4: Browser QA desktop**

Open `http://127.0.0.1:8001/` in the in-app browser or Playwright.

Verify:

- first-run language chooser can be dismissed by choosing a language
- first-run empty panel appears
- Add first prompt opens the editor
- Open Config opens Config
- sample-data command is visible
- there is no horizontal overflow

Save screenshot:

```text
G:\Temp\ipl-install-onboarding-desktop.png
```

- [ ] **Step 5: Browser QA mobile**

Use a 390x844 viewport.

Verify:

- first-run panel fits without horizontal overflow
- buttons remain tappable
- Config Local Setup section fits in drawer
- command hints do not overflow the viewport

Save screenshot:

```text
G:\Temp\ipl-install-onboarding-mobile.png
```

- [ ] **Step 6: CLI QA**

Run against the local scripts:

```bash
bash scripts/appctl.sh status
bash scripts/appctl.sh doctor
```

Expected:

- status prints short summary
- doctor prints headed sections
- no secrets are printed
- empty library next step mentions sample data

- [ ] **Step 7: Write QA note**

Create `docs/qa/2026-07-09-install-onboarding-polish-qa.md`:

```markdown
# Install and Onboarding Polish QA

## Automated

- `.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract tests/test_installer_release.py::test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values tests/test_installer_release.py::test_installed_status_reports_short_local_summary tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor -q`
- `npm run build`

## Manual Visual QA

- Desktop empty-library first-run panel: PASS/FAIL
- Mobile empty-library first-run panel: PASS/FAIL
- Config Local Setup desktop/mobile: PASS/FAIL
- No horizontal overflow: PASS/FAIL

## CLI QA

- `bash scripts/appctl.sh status`: PASS/FAIL
- `bash scripts/appctl.sh doctor`: PASS/FAIL

## Notes

- Full local pytest may still have known Windows/platform failures unrelated to this milestone.
```

Fill PASS/FAIL with actual results and include screenshot paths.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add docs/qa/2026-07-09-install-onboarding-polish-qa.md
git commit -m "docs: record install onboarding qa"
```

---

## Final Verification

- [ ] Run focused test suite:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py tests/test_installer_release.py tests/test_public_mvp.py -q
```

- [ ] Run frontend build:

```bash
npm run build
```

- [ ] Check git status:

```bash
git status --short --branch
```

- [ ] Use `superpowers:verification-before-completion` before claiming completion.
- [ ] Use `superpowers:requesting-code-review` or `superpowers:finishing-a-development-branch` before PR/merge decisions.

## Plan Self-Review

- Spec coverage: first-run UI is Task 1, Config setup is Task 2, doctor/status CLI is Task 3, docs are Task 4, verification and visual QA are Task 5.
- Marker scan: no incomplete markers or unspecified implementation steps remain.
- Type consistency: `emptyMode?: 'first-run' | 'no-results'`, `onOpenConfig?: () => void`, and command names are consistent across tasks.
