# Install and Onboarding Polish Design

## Milestone Goal

Improve the first successful local-install experience without rewriting the installer.

A new local user should be able to install the latest release, start the local app, understand why the library is empty, and choose one clear next action:

- add the first prompt
- install optional sample data
- connect optional generation
- run diagnostics if something looks wrong

This milestone is intentionally a small, verifiable polish pass. It should make the existing install path feel calmer and more self-explanatory, not introduce a new installer architecture.

## Context

Image Prompt Library already has:

- release-based install, update, rollback, service, uninstall, doctor, and sample-data commands
- a local-first web UI with add/edit/private library management
- a first-run language chooser
- optional ChatGPT / Codex OAuth generation in local installs
- read-only GitHub Pages demo behavior

Recent milestones completed Library Power-User Polish and Generation Hardening. The next product risk is that new users can install the app but still feel uncertain about the empty initial library, optional sample data, generation setup, update state, or diagnostics.

## Scope

### First-Run Empty Library Panel

Replace the generic empty state for true local empty libraries with a contextual first-run panel.

Show the first-run panel only when all of these are true:

- the app is not running in GitHub Pages demo mode
- the item list is empty
- there is no active search query
- there is no active collection filter

The panel should explain that an empty private library is expected after a fresh install and offer these actions:

- primary: add the first prompt
- secondary: open Config
- command hint: `image-prompt-library sample-data en`
- optional generation hint: connect ChatGPT / Codex OAuth in Config

If a search or filter returns no results, keep the existing no-results state. Search misses should not look like first-run onboarding.

### Config Local Setup Section

Add a compact Local Setup section near the top of Config.

The section should summarize:

- app version
- library path
- database path
- update status
- generation provider readiness
- optional sample-data command
- doctor/status command hints

This section is informational. It must not become a second settings system.

### CLI Doctor Polish

Keep `image-prompt-library doctor`, but make the output easier to act on.

Doctor output should use clear headings:

- App
- Library
- Database
- Generation
- Updates / Service
- Next steps

Each section should prefer `OK`, `WARN`, or `ERROR` style status lines over ambiguous prose. Private values and secrets must stay omitted or redacted.

Expected guidance:

- If item count is zero, suggest adding a prompt or running `image-prompt-library sample-data en`.
- If optional generation is not connected or not configured, suggest connecting generation in Config without implying it is required.
- If macOS service state is available, include the service label, state, plist path, and useful status/restart commands.

### Light CLI Status Command

Add `image-prompt-library status` as a short human-readable summary separate from verbose `image-prompt-library service status`.

Status should show:

- installed version
- library path
- backend URL from env/defaults
- database item count if accessible
- generation provider state
- macOS service state when on macOS

This is not a process monitor. It should be a small wrapper around existing local diagnostics.

### Documentation Cleanup

Update the public docs that shape first-run expectations:

- `README.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`
- `ROADMAP.md`

The docs should cover:

- current beta version
- first-run empty-library behavior
- optional sample-data installation
- `image-prompt-library doctor`
- `image-prompt-library status`
- WSL caveats
- native Windows PowerShell remaining out of scope

When touching these files, clean visible mojibake only in nearby edited lines. Avoid broad translation or formatting churn.

## Non-Goals

- No installer architecture rewrite.
- No native Windows PowerShell installer.
- No Docker Compose path.
- No account system.
- No import or external-inspiration work.
- No generation provider behavior changes beyond clearer onboarding links.
- No automatic sample-data install.
- No forced onboarding wizard.
- No new dependencies.

## UX Principles

- Keep onboarding contextual, not blocking.
- Give users one obvious primary action and a few quiet secondary paths.
- Preserve user freedom: no forced wizard, no locked tutorial overlay.
- Keep the local-first privacy model visible without turning the app into a marketing landing page.
- Use existing visual language and component patterns.
- Keep mobile layouts touch-friendly and avoid horizontal overflow.
- Preserve the GitHub Pages demo as read-only and informational.

## Components and Data Flow

### Frontend

`App.tsx` should decide whether the current item list represents a true first-run empty library or a normal no-results state. It can pass a focused empty-state mode into `CardsView`.

`CardsView.tsx` should render:

- existing no-results state for search/filter misses
- new first-run panel for local empty libraries

`ConfigPanel.tsx` should render the Local Setup section using existing config, update status, and provider status calls. It should avoid additional polling beyond what Config already does.

`i18n.ts` should add concise labels for the new panel and setup section in English, Traditional Chinese, and Simplified Chinese.

`styles.css` should extend the existing `.empty`, `.setting-group`, and responsive patterns rather than adding a separate design system.

### CLI

`scripts/appctl.sh` should keep the current `doctor` command and add a new `status` command.

The status command can share small helper logic with doctor where practical, but should not introduce a large shell abstraction. The implementation should stay readable and direct.

### Backend

No new persistent backend schema is required.

If the frontend needs no new API fields, avoid adding backend endpoints. Use existing `/api/config`, `/api/update-status`, `/api/generation-providers`, and item list data.

## Error Handling

- If Config cannot load provider status, keep the existing safe fallback and show an informational message.
- If update status cannot load, show a muted unavailable state rather than blocking the setup section.
- If `doctor` cannot open the database, print an `ERROR` line and continue with other sections where possible.
- If `status` cannot count items, print an unavailable database line instead of failing the whole command.

## Testing and Verification

Add focused automated coverage for:

- first-run empty state strings and actions in frontend static tests
- no-results state remaining distinct from first-run onboarding
- Config Local Setup section strings
- CLI usage including `status`
- doctor/status output headings and next-step hints
- docs mentioning `image-prompt-library status`
- public demo remaining read-only and not exposing local setup as live mutation controls

Manual QA should cover:

- desktop local empty library
- mobile local empty library
- search no-results state
- Config panel desktop/mobile
- `image-prompt-library doctor`
- `image-prompt-library status`

If practical after implementation, also run an installed-release smoke path on a temporary prefix and library path.

## Acceptance Criteria

- A fresh local empty library gives a clear first-run panel with add, Config, sample-data, and generation guidance.
- Search/filter no-results still shows the normal no-results state.
- Config shows local setup status without overwhelming the drawer.
- `image-prompt-library doctor` is easier to read and gives actionable next steps.
- `image-prompt-library status` exists and provides a short local summary.
- Docs explain first-run, sample-data, doctor, and status commands.
- GitHub Pages demo remains read-only.
- No new dependencies are introduced.
