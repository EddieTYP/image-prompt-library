# Install and Onboarding Polish QA

## Automated

- PASS: `.\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract tests/test_installer_release.py::test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values tests/test_installer_release.py::test_installed_status_reports_short_local_summary tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor -q -p no:cacheprovider`
  - Result: `67 passed, 1 warning in 19.21s`
  - Warning: existing Starlette/httpx deprecation warning.
- PASS: `npm run build`

## Manual Visual QA

- PASS: Desktop empty-library first-run panel appears for a fresh local library.
- PASS: Desktop `Add your first prompt` opens the new reference editor.
- PASS: Desktop Config Local Setup section is visible with `status`, `doctor`, and `sample-data en` commands.
- PASS: Mobile empty-library first-run panel fits without horizontal overflow.
- PASS: Mobile first-run hides the floating Add, Generate, and generation queue controls so they cannot cover onboarding content.
- PASS: Mobile buttons remain tappable.
- PASS: Mobile Config Local Setup section fits in the drawer.
- PASS: Mobile command hints do not overflow the viewport.
- PASS: No horizontal overflow detected on desktop or mobile.

Screenshots:

- `G:\Temp\ipl-install-onboarding-desktop.png`
- `docs/qa/screenshots/install-onboarding-mobile-empty.png`
- `docs/qa/screenshots/install-onboarding-mobile-config.png`

Mobile screenshot method:

- The browser viewport was set so the page had a measured `375px` CSS content width.
- Both states used viewport captures from fresh tabs after the `220ms` drawer transition settled. Full-page capture is not valid because the browser temporarily resizes the page and can mis-composite fixed or transformed drawers.
- Measured results: document `scrollWidth` was `375px`; the first-run panel stayed within the viewport; floating rail and queue trigger counts were both `0`; the settled Config drawer started at `x=0` and its visible header ended at `x=357.2`.
- The earlier `G:\Temp\ipl-install-onboarding-mobile.png` is superseded because it captured the fixed drawer incorrectly and is not valid QA evidence.

## CLI QA

- PASS: `bash scripts/appctl.sh status`
  - Printed a short local summary with version, library path, URL, item count, generation state, service state, and doctor hint.
- PASS: `bash scripts/appctl.sh doctor`
  - Printed headed sections for app, library, database, generation, updates/service, and next steps.
  - Empty-library next step mentions `image-prompt-library sample-data en`.
  - No tokens, client secrets, or `app_` secret values were printed.

## Notes

- Local Git Bash on this Windows machine does not provide `python3`, so CLI QA used `PYTHON=G:/Codex/image-prompt-library/.venv/Scripts/python.exe`, matching the Windows-compatible installer tests.
- The QA server used `G:\Temp\ipl-onboarding-empty-library` on `http://127.0.0.1:8001/`.
