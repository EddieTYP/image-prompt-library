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
- Post-live-QA fix recheck:
  - `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py -q`: PASS, `60 passed`.
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
- OAuth/session: PASS after user approved the OpenAI device flow in the in-app browser.
- Provider status from `/api/generation-providers`:
  - `configured: true`
  - `authenticated: true`
  - `available: true`
  - `state: connected`
  - `status: ready`
  - `can_generate: true`
  - `features.text_to_image: true`
  - `features.text_reference_to_image: true`
  - `features.image_edit: true`
- Prompt: `A small friendly robot watering a single sunflower, clean studio illustration, soft daylight.`
- Settings:
  - provider: `openai_codex_oauth_native`
  - image model: `gpt-image-2`
  - orchestrator model: `gpt-5.4`
  - quality: `low`
  - requested aspect ratio: `auto`
- Job flow:
  - Created job `gen_6d6a6ba4e3954838`.
  - Job entered `running`.
  - Job completed with `status: succeeded`.
  - Result file: `generation-results/gen_6d6a6ba4e3954838/result-0c4b3d1a863f.png`.
  - Result dimensions: `1254x1254`.
  - Result sha256: `0c4b3d1a863fd104c35e71a92386ef304c0a09529a81c84c5b587cbac0d0ed6e`.
- Visual QA follow-up:
  - Desktop screenshot after live auth/generation fix: `G:\Temp\ipl-generation-hardening-live-desktop.png`.
  - Mobile screenshot after live auth/generation fix: `G:\Temp\ipl-generation-hardening-live-mobile.png`.
  - Desktop provider readiness compact label no longer breaks provider text into one-letter lines; compact bar shows `Ready` and retains the full provider readiness label as tooltip/aria text.
  - Mobile 390x844 compact controls fit without horizontal page overflow: `innerWidth=390`, `documentScrollWidth=390`, `bodyScrollWidth=390`, `hasHorizontalOverflow=false`.
  - Generate and History controls remain visible on mobile after tightening control gap/padding.
- Failure message, if any: none during the live job.
- Retry/recovery: not exercised for the live provider because the first live job succeeded.

## Release Gate

- Automated focused tests passed: yes.
- Frontend static tests passed: yes.
- Frontend build passed: yes.
- Desktop QA recorded: yes.
- Mobile QA recorded: yes.
- Live provider QA recorded: yes.

Release gate is satisfied for the focused Generation Hardening milestone. Full `pytest -q` still has the previously recorded Windows/platform failures and should not be treated as a milestone regression.
