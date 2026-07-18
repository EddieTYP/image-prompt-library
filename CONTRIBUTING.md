# Contributing

Thanks for considering a contribution to Image Prompt Library.

This project is a Local-first prompt/image reference manager. Please preserve the privacy-first design: user runtime data belongs on the user's device and should not be committed, uploaded, or sent to third-party services by default.

## License model

The core application code is licensed under **AGPL-3.0-or-later**. By contributing, you agree that your contribution is submitted under AGPL-3.0-or-later and may be included in versions distributed under alternative/commercial licensing terms by the project maintainer.

Sample data and third-party assets are licensed separately and retain their original attribution/license terms.


## Local setup

```bash
./scripts/setup.sh
./scripts/dev.sh
```

For single-service local mode:

```bash
./scripts/start.sh
```

## Run tests

Before opening a PR, run:

```bash
source .venv/bin/activate
python -m pytest -q
npm run test:frontend
npm run build
```

If you have a running local server, also run:

```bash
./scripts/smoke-test.sh
```

## Release assets

Release tags must use `v<major>.<minor>.<patch>` with an optional SemVer prerelease suffix, such as `v1.2.3` or `v1.2.3-rc.1`. Build-metadata suffixes (`+...`) are not accepted because release asset filenames must remain exact. Manual release workflow dispatches are candidate-only and must run from `main`: the workflow binds the schema-v2 manifest to that commit, verifies the package locally, creates the exact tag only after those checks, uploads only the archive, checksum, and manifest to a draft release, downloads them back through the GitHub API, verifies them again, and publishes the release as a prerelease without changing GitHub Latest. If a run stops after creating the draft, rerunning the same tag removes only those exact expected draft assets and resumes the gate. If publication completed, an exact three-asset published prerelease is reverified idempotently; incomplete, duplicate, unknown, orphaned, or retargeted release state is retained and rejected for manual review. Do not publish a draft or stable release manually without completing the same verification.

Before promoting a bare candidate tag, run the manual `Release candidate install update rollback smoke` workflow against the current stable baseline. It uses public assets and default user paths on Windows, macOS, and Ubuntu. Leave the release marked as a prerelease if any platform fails. After every job passes, update that existing GitHub release to `prerelease=false` and `make_latest=true`, then verify `/releases/latest` points to the same release ID; do not retag or re-upload the assets.

Manual `scripts/package-release.sh --skip-build` runs must set `IMAGE_PROMPT_LIBRARY_SOURCE_SHA` to the exact 40-character commit for the controlled frontend build being packaged; normal release workflow runs set this automatically after building.

## Development guidelines

- Keep runtime data out of git:
  - `library/db.sqlite`
  - `library/db.sqlite-*`
  - `library/originals/`
  - `library/thumbs/`
  - `library/previews/`
  - `backups/`
- Avoid hardcoded absolute paths in public docs or scripts.
- Keep local agent state, QA captures, generated artifacts, machine-specific paths, usernames, credentials, and private prompts/images out of git.
- Treat `.agents/`, `.codex/`, `.codex-qa-*`, `.codebase-memory/`, `.qa-*`, `.superpowers/`, `docs/plans/`, and `docs/qa/` as local-only.
- Stage explicit paths only; never use `git add .` or `git add -A`.
- Before committing, inspect `git status --short`, `git diff --cached --name-status`, and `git diff --cached`.
- Before pushing, inspect `git diff --name-status origin/main...HEAD`.
- Keep `/media` limited to intended image media directories; never expose the SQLite DB or internal files.
- Prefer small, tested changes.
- Add regression tests for bug fixes and public-install behavior.
- Preserve the accepted browsing model: Explore is a thumbnail constellation; Cards is adaptive masonry.

## Reporting issues

When reporting a bug, include:

- OS and browser
- Python and Node versions
- Whether you use dev mode or `scripts/start.sh`
- Steps to reproduce
- Console/server error output if available
- Whether your library is empty, manually created, or imported

Do not attach private prompt/image data unless you intentionally want it public.
