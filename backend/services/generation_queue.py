from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from backend.services.generation_jobs import GenerationJobRepository
from backend.services.openai_codex_native import PROVIDER_ID, OpenAICodexNativeProvider

MAX_CONCURRENT_GENERATION_JOBS = 2

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_GENERATION_JOBS, thread_name_prefix="generation-job")
_lock = Lock()
_active: set[str] = set()


def enqueue_generation_jobs(library_path: Path | str, *, provider: str = PROVIDER_ID) -> None:
    """Start queued provider jobs up to the local concurrency cap.

    This is intentionally in-process/local-first. Queued jobs persist in SQLite; the
    active set only protects the current app process from launching more than two
    provider calls at once.
    """
    library = Path(library_path)
    with _lock:
        available = MAX_CONCURRENT_GENERATION_JOBS - len(_active)
        if available <= 0:
            return
        repo = GenerationJobRepository(library)
        queued = repo.next_queued_provider_jobs(provider, limit=available)
        for job in queued:
            _active.add(job.id)
            _executor.submit(_run_job_and_continue, library, job.id, provider)


def _run_job_and_continue(library_path: Path, job_id: str, provider: str) -> None:
    try:
        OpenAICodexNativeProvider().run_job(library_path, job_id)
    except Exception:
        # Provider/repository code records failed/cancelled state where possible.
        # The queue runner must never die because one job failed.
        pass
    finally:
        with _lock:
            _active.discard(job_id)
        enqueue_generation_jobs(library_path, provider=provider)
