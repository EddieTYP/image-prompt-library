# Task 2 Report: Stale Timeout, Recovery, Retry, And Cancel Coverage

## Scope

Implemented the Task 2 brief in `backend/services/generation_jobs.py` and `tests/test_generation_jobs.py` on branch `codex/generation-hardening`, without changing queue/retry/restart-recovery design.

## TDD Evidence

### Red

1. Added the required stale timeout, retry, cancel, and restart recovery coverage to `tests/test_generation_jobs.py`:
   - `_make_running_job`
   - `test_running_generation_job_is_not_stale_before_ten_minutes`
   - `test_stale_running_generation_job_fails_with_retryable_message`
   - `test_queued_and_running_generation_jobs_can_be_cancelled`
   - `test_recover_interrupted_generation_jobs_marks_only_provider_running_failed`
2. Ran:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_generation_jobs.py -q
   ```

3. Confirmed the new stale test failed before implementation for the expected reason:
   - `test_stale_running_generation_job_fails_with_retryable_message`
   - failure: `Generation job is not stale yet; wait about 19 more minute(s)`
   - this showed production still used the old 30-minute threshold

### Green

1. Updated only the required production constants in `backend/services/generation_jobs.py`:

   ```python
   STALE_RUNNING_JOB_AFTER = timedelta(minutes=10)
   STALE_RUNNING_JOB_ERROR = "Generation took too long and may have stalled. Retry to run it again."
   ```

2. Ran focused task verification:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_generation_jobs.py -q -k "running_generation_job_is_not_stale_before_ten_minutes or stale_running_generation_job_fails_with_retryable_message or queued_and_running_generation_jobs_can_be_cancelled or recover_interrupted_generation_jobs_marks_only_provider_running_failed"
   ```

3. Result:
   - `4 passed, 36 deselected`

## Files Changed

- `backend/services/generation_jobs.py`
- `tests/test_generation_jobs.py`
- `.superpowers/sdd/task-2-report.md`

## Tests Run

### Task-specific passing verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_generation_jobs.py -q -k "running_generation_job_is_not_stale_before_ten_minutes or stale_running_generation_job_fails_with_retryable_message or queued_and_running_generation_jobs_can_be_cancelled or recover_interrupted_generation_jobs_marks_only_provider_running_failed"
```

- Result: passed

### Requested broader suite

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q
```

- Result: 2 pre-existing failures on this Windows environment:
  - `test_codex_native_token_store_is_app_owned_redacted_and_permissioned`
    - expected `0o600`, got `0o666`
  - `test_codex_native_marks_failed_when_stage_result_rejects_unsafe_result_root`
    - symlink creation failed with `WinError 1314`

### Full generation jobs file after change

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_generation_jobs.py -q
```

- Result: task tests passed, but unrelated existing failures remain:
  - path separator expectation (`originals/` vs `originals\...`) on Windows
  - multiple symlink permission failures with `WinError 1314`

## Self-Review

- Kept production change minimal: constants only, exactly as requested.
- Added the exact backend coverage requested for stale timeout threshold, stale failure message, retry metadata, cancel support, and provider-scoped restart recovery.
- Did not redesign restart recovery, queueing, or retry behavior.
- Did not touch unrelated failing platform-specific tests.

## Remaining Risk

- The repo has existing Windows-specific test failures unrelated to Task 2, so the full requested files do not go fully green in this environment even though the Task 2 coverage does.
