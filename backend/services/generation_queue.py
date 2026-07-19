from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import BoundedSemaphore, RLock, Timer

from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository
from backend.services.openai_codex_native import (
    PROVIDER_ID,
    CodexNativeRateLimitError,
    OpenAICodexNativeProvider,
)

MAX_CONCURRENT_GENERATION_JOBS = 5
QUEUE_RESUME_RETRY_SECONDS = 5
INTERRUPTED_BY_BACKEND_RESTART_ERROR = (
    "Generation job was interrupted by backend restart. Retry to run it again."
)

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_GENERATION_JOBS, thread_name_prefix="generation-job")
_lock = RLock()
_active: set[str] = set()
_pause_timers: dict[tuple[str, str], Timer] = {}
_provider_slots = BoundedSemaphore(MAX_CONCURRENT_GENERATION_JOBS)


def recover_interrupted_generation_jobs(library_path: Path | str, *, provider: str = PROVIDER_ID):
    """Fail persisted running jobs left behind by a prior backend process.

    The queue runner is process-local, so running jobs from a previous backend
    process do not have a live provider request or worker in this process.
    Mark them failed instead of silently rerunning paid/non-idempotent generation.
    Persisted queued jobs are still safe to drain because they have not started.
    """
    repo = GenerationJobRepository(Path(library_path))
    return repo.mark_running_provider_jobs_failed(provider, INTERRUPTED_BY_BACKEND_RESTART_ERROR)


def enqueue_generation_jobs(library_path: Path | str, *, provider: str = PROVIDER_ID) -> None:
    """Start queued provider jobs up to the local concurrency cap.

    This is intentionally in-process/local-first. Queued jobs persist in SQLite; the
    active set only protects the current app process from launching more than five
    provider calls at once.
    """
    library = Path(library_path)
    with _lock:
        repo = GenerationJobRepository(library)
        state = repo.get_provider_queue_state(provider)
        if state.paused:
            _schedule_pause_wake(library, provider, state.retry_after_seconds)
            return
        available = MAX_CONCURRENT_GENERATION_JOBS - len(_active)
        if available <= 0:
            return
        queued = repo.next_queued_provider_jobs(provider, limit=available)
        if not queued:
            repo.clear_provider_backoff_if_drained(provider, active_count=len(_active))
            return
        repo.mark_provider_wave_started(provider)
        for job in queued:
            _active.add(job.id)
            _executor.submit(_run_job_and_continue, library, job.id, provider)


def _run_job_and_continue(library_path: Path, job_id: str, provider: str) -> None:
    try:
        _provider_slots.acquire()
        try:
            OpenAICodexNativeProvider().run_job(library_path, job_id)
        finally:
            _provider_slots.release()
    except CodexNativeRateLimitError as exc:
        GenerationJobRepository(library_path).record_provider_rate_limit(provider, exc.retry_after_seconds)
    except Exception:
        # Provider/repository code records failed/cancelled state where possible.
        # The queue runner must never die because one job failed.
        pass
    finally:
        with _lock:
            _active.discard(job_id)
        _continue_generation_queue(library_path, provider)


def run_generation_job_now(library_path: Path | str, job_id: str):
    """Run a synchronous native job without exceeding the shared provider cap."""
    if not _provider_slots.acquire(blocking=False):
        raise GenerationJobConflict("The generation provider is at its concurrency limit; wait for a running job to finish")
    try:
        return OpenAICodexNativeProvider().run_job(Path(library_path), job_id)
    finally:
        _provider_slots.release()


def _schedule_pause_wake(library_path: Path, provider: str, delay_seconds: int) -> None:
    key = (str(library_path.resolve()), provider)
    delay = max(0.01, float(delay_seconds or 0))
    with _lock:
        timer = _pause_timers.get(key)
        if timer is not None and timer.is_alive():
            return

        def wake() -> None:
            with _lock:
                _pause_timers.pop(key, None)
            _continue_generation_queue(library_path, provider)

        timer = Timer(delay, wake)
        timer.daemon = True
        _pause_timers[key] = timer
        timer.start()


def _continue_generation_queue(library_path: Path, provider: str) -> None:
    try:
        enqueue_generation_jobs(library_path, provider=provider)
    except (OSError, sqlite3.Error):
        _schedule_pause_wake(library_path, provider, QUEUE_RESUME_RETRY_SECONDS)
