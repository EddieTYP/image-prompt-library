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
- PASS: Mobile buttons remain tappable.
- PASS: Mobile Config Local Setup section fits in the drawer.
- PASS: Mobile command hints do not overflow the viewport.
- PASS: No horizontal overflow detected on desktop or mobile.

Screenshots:

- `G:\Temp\ipl-install-onboarding-desktop.png`
- `G:\Temp\ipl-install-onboarding-mobile.png`

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
