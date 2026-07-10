# Task 3 Report: CLI Doctor Polish and Status Command

## Summary

Implemented the local CLI diagnostics polish for install/onboarding:

- Updated `image-prompt-library doctor` output into clear sections:
  - `## App`
  - `## Library`
  - `## Database`
  - `## Generation`
  - `## Updates / Service`
  - `## Next steps`
- Added `image-prompt-library status` for a shorter local summary.
- Kept private generation values out of CLI output.
- Added regression coverage for the new `doctor` and `status` output.
- Fixed Windows/Git Bash install compatibility found while validating the new CLI tests:
  - Strip `\r` from the manifest SHA emitted by Windows Python before checksum comparison.
  - Extract release tarballs from the download directory so `tar` does not treat `G:/...` as a remote host.
  - Use a local Git Bash test helper for Windows-focused installer tests.

## Verification

Passed:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'; .\.venv\Scripts\python.exe -m pytest tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract tests/test_installer_release.py::test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values tests/test_installer_release.py::test_installed_status_reports_short_local_summary -q
```

Result:

```text
3 passed, 1 warning in 17.49s
```

Passed:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n scripts/install.sh
& 'C:\Program Files\Git\bin\bash.exe' -n scripts/appctl.sh
```

## Notes

The pytest warning is the existing local `.pytest_cache` permission warning and did not affect test results.
