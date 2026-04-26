# Roadmap

## Public AGPL local-install MVP

Goal: make Image Prompt Library easy for someone to clone from GitHub, run on their own device, and use as an open-source local-first prompt/image manager under AGPL-3.0-or-later. Commercial licenses are available for organizations that need terms outside the AGPL.

### Must-have before public alpha

- Public-facing README with generic install instructions and no machine-specific absolute paths.
- One-command setup and start scripts.
- Clear `.env.example` configuration for library path, host, and ports.
- Friendly first-run behavior with an empty library and obvious Add CTA.
- Backup and restore guidance for runtime data.
- Smoke-test script for a running local instance.
- Tests/build passing from a fresh checkout.
- Runtime data ignored by git.
- AGPL-3.0-or-later license wording plus clear commercial license option for non-AGPL terms.
- `/media` route must not expose database, config, or internal files.

### Correctness hardening

- Prefer `result_image` for card/detail hero images.
- Treat only `result_image` as satisfying required result-image checks.
- Add DB-level validation for image roles.
- Clean up or roll back prompt-only items if required image upload fails.
- Verify optional sample-library install idempotency.

### Nice-to-have after public alpha

- Native Windows PowerShell scripts or a Docker Compose local install path; WSL 2 is the practical Windows route for now.
- Sample/demo dataset or screenshots that do not include private runtime data.
- Export/import backup archive workflow in the UI.
- Full interface language setting.
- Better mobile polish.
- Optional semantic/vector search.

## Current non-goals

- Hosted SaaS accounts.
- Built-in cloud sync.
- Public prompt sharing.
- Committing user runtime data into the repository.
