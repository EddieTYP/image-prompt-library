# Generation Hardening Live QA

Date: 2026-07-08

## Automated Checks

- `pytest -q`: FAIL on this native Windows environment.
  - First run failed broadly because Python used the local `cp950` text codec for UTF-8 source/static files.
  - Re-run with `PYTHONUTF8=1` reduced the failures to existing Windows/platform issues plus two stale frontend static expectations.
  - The two stale frontend static expectations were fixed in commit `69e2af5`.
  - Remaining failures are platform/environmental and pre-existing to this milestone:
    - file release update lookup returns no latest version on Windows file URI path
    - symlink tests fail with `WinError 1314` because the process lacks symlink privilege
    - image path assertions expect POSIX separators while Windows returns backslashes
    - installer/sample-data tests expect Unix shell utilities such as `dirname`
    - token-store mode assertion expects POSIX file permissions
- `PYTHONUTF8=1 pytest tests/test_frontend_static.py -q`: PASS, `60 passed`.
- Focused Task 1-4 tests: PASS as recorded in task reports.
- `npm run build`: PASS.

## Desktop Visual QA

- Viewport: 1440x900
- URL: `http://127.0.0.1:8000/`
- Local QA library: `G:\Temp\ipl-generation-hardening-library`
- Screenshot: `G:\Temp\ipl-generation-hardening-desktop.png`

Observed:

- Standalone `Generate` action is visible and does not overlap the queue trigger.
- Queue trigger is visible and clear of bottom actions.
- Generation panel opens.
- Provider readiness is visible: `Manual upload ready`.
- Aspect ratio, quality, model, attachment, generate, and history controls are visible.
- Compact controls stay on one row at desktop width.
- Manual generation job creation succeeds with writable temp library.
- Queue drawer shows `0 running · 1 queued · 0 ready`.
- Queued job row shows prompt, status, and `Cancel`.
- No desktop action overlap observed.

## Mobile Visual QA

- Viewport: 390x844
- URL: `http://127.0.0.1:8000/`
- Screenshot: `G:\Temp\ipl-generation-hardening-mobile.png`

Observed:

- Bottom `Add` and `Generate` actions are visible.
- Queue trigger is above the bottom actions and does not overlap them.
- Queue drawer opens and remains usable.
- Queue drawer width fits the mobile viewport.
- Queued job row fits within drawer width.
- Generation panel opens on mobile.
- Provider readiness wraps onto its own line: `Manual upload ready`.
- Model/settings controls remain visible.
- Generate and History controls fit without overlap.

## Live OAuth / Generation QA

- Provider: `openai_codex_oauth_native`
- OAuth/session: BLOCKED
- Provider status from `/api/generation-providers`:
  - `configured: true`
  - `authenticated: false`
  - `available: false`
  - `state: not_connected`
  - `status: login_required`
  - `can_generate: false`
  - `message: Connect ChatGPT / Codex OAuth before generating.`
- Prompt: not submitted to live provider.
- Settings: not submitted to live provider.
- Job flow: manual-upload fallback job was created and queued; live provider job was not created.
- Result: live OAuth and full live generation require the user to reconnect/approve the provider session.
- Failure message, if any: app correctly reports provider login required via provider readiness fields.
- Retry/recovery: not exercised for live provider because OAuth is not authenticated.

## Release Gate

- Automated focused tests passed: yes.
- Frontend static tests passed: yes.
- Frontend build passed: yes.
- Desktop QA recorded: yes.
- Mobile QA recorded: yes.
- Live provider QA recorded: blocked on user OAuth re-authentication.

This milestone should not be released until live OAuth and one full live generation attempt are completed with the user present.
