# Versioned Installer / Updater Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Let normal users install or update Image Prompt Library by selecting a tagged version, without cloning the repo or repeatedly running `git pull`.

**Architecture:** Ship a release artifact that contains the backend, built frontend `dist/`, scripts, public docs, license files, and a manifest/checksum. A small bootstrap installer downloads one tagged release asset into a versioned app directory, keeps user data outside the app directory, points `current` at the selected version, and provides update/rollback commands. GitHub Pages remains read-only; local private data remains local and untouched by app upgrades.

**Tech Stack:** Bash installer for macOS/Linux/WSL, Python helper for manifest/checksum validation and portable filesystem operations, existing FastAPI backend, prebuilt Vite frontend, GitHub Releases assets.

---

## Product decision

Do this before Batch 5 generic URL + X/Threads import.

Batch 5 remains the next feature batch after install/update is less painful. The installer should make the app usable by people who do not want to understand git, branches, or pulling the whole repo.

## Non-goals for this pass

- No native macOS `.app` bundle yet.
- No signed/notarized installer yet.
- No Windows PowerShell-native flow yet; WSL 2 stays supported through the Bash path.
- No automatic background updates.
- No SaaS accounts, hosted sync, payment, checkout, or cloud library.

## Desired user experience

### Fresh install

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
```

Optional explicit version:

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash -s -- --version v0.4.0-alpha
```

Installer behavior:

1. Detect OS and required commands.
2. Require Python 3.10+.
3. Do **not** require Node.js for normal users because the release artifact includes built frontend assets.
4. Download release manifest and app tarball from GitHub Releases.
5. Verify SHA256 checksum.
6. Extract to:
   ```text
   ~/.image-prompt-library/app/versions/<version>/
   ```
7. Create/update:
   ```text
   ~/.image-prompt-library/app/current -> versions/<version>
   ```
8. Create default config if missing:
   ```text
   ~/.image-prompt-library/.env
   ```
9. Default private library path:
   ```text
   ~/ImagePromptLibrary
   ```
10. Create command shim when possible:
    ```text
    ~/.local/bin/image-prompt-library
    ```
11. Print start command and local URL.

### Start installed app

```bash
image-prompt-library start
```

Fallback:

```bash
~/.image-prompt-library/app/current/scripts/appctl.sh start
```

### Update to latest

```bash
image-prompt-library update
```

### Update to a specific version

```bash
image-prompt-library update --version v0.4.0-alpha
```

### Rollback

```bash
image-prompt-library rollback
```

Rollback should repoint `current` to the previous extracted version only after confirming that version exists. It must not mutate/delete the user library.

## Runtime layout

```text
~/.image-prompt-library/
  .env
  auth.json                       # optional Codex auth, if user uses generation
  app/
    current -> versions/v0.4.0-alpha
    previous -> versions/v0.3.0-alpha
    downloads/
    versions/
      v0.3.0-alpha/
      v0.4.0-alpha/
  logs/

~/ImagePromptLibrary/
  db.sqlite
  originals/
  previews/
  thumbs/
  generation-results/
  imports/
```

Important boundary: app code is replaceable; user runtime data and auth/config are not inside the versioned app directory.

## Release artifact shape

For each tag, CI should create release assets:

```text
image-prompt-library-<version>.tar.gz
image-prompt-library-<version>.tar.gz.sha256
image-prompt-library-<version>.manifest.json
```

Manifest example:

```json
{
  "name": "image-prompt-library",
  "version": "v0.4.0-alpha",
  "schema_version": 1,
  "artifact": "image-prompt-library-v0.4.0-alpha.tar.gz",
  "sha256": "...",
  "python": ">=3.10",
  "node_required_for_runtime": false,
  "built_frontend": true,
  "created_at": "2026-04-29T00:00:00Z"
}
```

Tarball should include:

```text
backend/
dist/
scripts/appctl.sh
scripts/setup-runtime.sh
pyproject.toml
README.md
LICENSE
NOTICE
SECURITY.md
```

Tarball should exclude:

```text
.git/
.venv/
node_modules/
library/
backups/
.local-work/
.env
*.sqlite
```

## Task 1: Document installer posture in roadmap

**Objective:** Make the priority shift explicit before implementation.

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/PROJECT_STATUS.md`

**Steps:**
1. Add a short `Versioned installer / updater` section before `Import and agent-ingestion roadmap`.
2. State that Batch 5 is paused until installer/update UX is available.
3. State app code/data boundary and no-git-pull goal.
4. Run:
   ```bash
   python -m pytest tests/test_public_mvp.py::test_public_docs_do_not_use_edward_specific_setup_paths -q
   ```

## Task 2: Add failing tests for installer docs and scripts

**Objective:** Lock the public contract before implementation.

**Files:**
- Modify: `tests/test_public_mvp.py`
- Create or modify: `tests/test_installer_release.py`

**Test expectations:**

- `scripts/install.sh` exists.
- `scripts/appctl.sh` exists.
- README mentions non-git installer path.
- README still keeps clone/dev path.
- Installer does not contain `8787`.
- Installer uses GitHub Release assets, not `git pull`.
- Installer has `--version` support.
- Installer keeps app code under `~/.image-prompt-library/app/versions`.
- Installer defaults library data outside the app directory.
- Release packaging script excludes runtime/private files.

**Run RED:**

```bash
python -m pytest tests/test_installer_release.py -q
```

Expected: fail because files/scripts do not exist yet.

## Task 3: Create runtime setup helper

**Objective:** Set up per-version Python venv without Node.

**Files:**
- Create: `scripts/setup-runtime.sh`

**Behavior:**

- `cd` to app root.
- Check Python 3.10+.
- Create `.venv` inside the versioned app directory if missing.
- Install backend runtime deps:
  ```bash
  python -m pip install --upgrade pip
  python -m pip install .
  ```
- Do not run `npm install`.
- Do not write into the user library.

**Run GREEN:**

```bash
bash -n scripts/setup-runtime.sh
python -m pytest tests/test_installer_release.py -q
```

## Task 4: Create app control script

**Objective:** Provide stable `start`, `version`, `update`, and `rollback` commands for installed users.

**Files:**
- Create: `scripts/appctl.sh`

**Initial behavior:**

```bash
scripts/appctl.sh start
scripts/appctl.sh version
scripts/appctl.sh update --version <tag>
scripts/appctl.sh rollback
```

Start command:

- Load `~/.image-prompt-library/.env` if present.
- Default:
  ```bash
  IMAGE_PROMPT_LIBRARY_PATH=~/ImagePromptLibrary
  BACKEND_HOST=127.0.0.1
  BACKEND_PORT=8000
  ```
- Use app-local `.venv/bin/python` when available.
- Run:
  ```bash
  python -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ```
- Serve built `dist/` through FastAPI as existing `backend.main:app` does.

## Task 5: Create bootstrap installer

**Objective:** Install a tagged release asset without git clone/pull.

**Files:**
- Create: `scripts/install.sh`

**Behavior:**

- Parse:
  ```text
  --version <tag>
  --prefix <path>              default ~/.image-prompt-library
  --library-path <path>        default ~/ImagePromptLibrary
  --no-shim
  ```
- Resolve `latest` to the newest GitHub release/tag.
- Download manifest + tarball + sha256.
- Verify checksum before extract.
- Extract into `app/versions/<version>`.
- Run `scripts/setup-runtime.sh` inside extracted app.
- Atomically update `app/current` symlink.
- Preserve `app/previous` symlink for rollback.
- Create `.env` only if missing.
- Create `~/.local/bin/image-prompt-library` shim if possible.
- Print next steps.

Security constraints:

- `set -euo pipefail`.
- Never print tokens/secrets.
- Never delete `~/ImagePromptLibrary`.
- Never overwrite existing `.env` without explicit user flag.
- Refuse to install into `/`, `$HOME`, or a non-empty unsafe path unless it is the expected prefix layout.

## Task 6: Add release packaging script

**Objective:** Generate the exact artifact CI will upload.

**Files:**
- Create: `scripts/package-release.sh`

**Behavior:**

```bash
scripts/package-release.sh v0.4.0-alpha
```

- Run `npm run build`.
- Create staging directory.
- Copy only release-safe files.
- Include built `dist/`.
- Exclude runtime/private/generated folders.
- Create tarball, sha256, manifest.
- Output to `dist-release/`.

Tests should assert exclusion patterns include `.env`, `.local-work`, `library`, `node_modules`, `.venv`, `backups`.

## Task 7: Add GitHub Actions release packaging workflow

**Objective:** Build release assets from tags.

**Files:**
- Create: `.github/workflows/release-assets.yml`

**Behavior:**

- Trigger on tags matching `v*` and manual dispatch.
- Setup Python/Node.
- Install deps.
- Run tests and `npm run build`.
- Run `scripts/package-release.sh "$GITHUB_REF_NAME"`.
- Upload assets to the GitHub Release.

First pass can use `softprops/action-gh-release` or `gh release upload`; prefer a simple action with minimal permissions.

## Task 8: Update README quick start

**Objective:** Make installer path the normal-user path, keep git clone for dev/contributors.

**Files:**
- Modify: `README.md`

**Copy structure:**

```markdown
## Quick start for normal users

Install latest tagged release without cloning the repo:
...

## Developer setup from source

Use this if you want to develop, inspect source, or run unreleased main:
...
```

Rules:

- Keep `Add/Edit/private library management local-only` clear.
- Keep public demo read-only wording.
- Keep Python 3.10+ requirement.
- State Node.js is only required for source/development installs, not release installer path.

## Task 9: Verify installer locally using a fake release directory

**Objective:** Prove installer logic without publishing a real GitHub release asset.

**Approach:** Add a test mode/env var such as:

```bash
IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL=file:///tmp/fake-release
```

Then generate a fake release using `scripts/package-release.sh`, install into a temp prefix, and verify:

- `app/current` points to requested version.
- `.env` exists and points library data outside app.
- `.venv/bin/python` exists.
- `scripts/appctl.sh version` prints expected version.
- `scripts/appctl.sh start` can serve `/api/health` on a non-8787 port.

## Task 10: Full verification and commit

Run:

```bash
python -m pytest tests/test_installer_release.py tests/test_public_mvp.py tests/test_public_ci_release.py -q
npm run build
python -m pytest -q
python -m compileall -q backend scripts
git diff --check
```

Then commit:

```bash
git add README.md ROADMAP.md docs/PROJECT_STATUS.md docs/plans/versioned-installer-updater.md scripts/install.sh scripts/appctl.sh scripts/setup-runtime.sh scripts/package-release.sh .github/workflows/release-assets.yml tests/test_installer_release.py tests/test_public_mvp.py
git commit -m "feat: add versioned release installer"
```

## Open questions to decide during implementation

1. Should `image-prompt-library update` default to latest stable release only, or include alpha tags while project is alpha-only?
   - Recommended now: latest GitHub release, including alpha, because all current tags are alpha.
2. Should the installer install sample data by default?
   - Recommended: no. Keep private library empty by default; offer `install-sample-data` separately.
3. Should installed users have a launchd/systemd service?
   - Recommended: not in first pass. Keep manual `start` simple.
4. Should release artifacts bundle Python wheels?
   - Recommended: no for first pass; use pip from PyPI. Wheelhouse can be a later offline-install enhancement.

## Acceptance criteria

- A non-developer can install a tagged release without `git clone` or `git pull`.
- Normal installed runtime does not require Node.js.
- User library data survives app update/rollback.
- Installer supports explicit version pinning.
- Release artifact excludes runtime/private/generated data.
- Public docs make installer path clear without turning Pages into SaaS/account/payment flow.
- Tests and build pass.
