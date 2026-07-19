#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.schemas import GenerationJobCreate
from backend.config import validate_app_owned_paths
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository, sanitize_generation_error
from backend.services.openai_codex_native import (
    IMAGE_MODEL,
    PROVIDER_ID,
    CodexDeviceCodeFlow,
    CodexNativeAuthError,
    CodexNativeAuthStore,
    OpenAICodexNativeProvider,
)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _print_json(value: Any) -> None:
    print(json.dumps(_jsonable(value), ensure_ascii=False, indent=2))


def status(args: argparse.Namespace) -> int:
    del args
    _print_json(CodexNativeAuthStore().status())
    return 0


def start(args: argparse.Namespace) -> int:
    del args
    _print_json(CodexDeviceCodeFlow().start())
    return 0


def poll(args: argparse.Namespace) -> int:
    _print_json(CodexDeviceCodeFlow().poll_device_authorization(args.device_auth_id, args.user_code))
    return 0


def disconnect(args: argparse.Namespace) -> int:
    del args
    store = CodexNativeAuthStore()
    store.delete_tokens()
    _print_json(store.status())
    return 0


def generate(args: argparse.Namespace) -> int:
    library_path = Path(args.library).expanduser()
    repo = GenerationJobRepository(library_path)
    job = repo.create_job(
        GenerationJobCreate(
            provider=PROVIDER_ID,
            model=IMAGE_MODEL,
            prompt_text=args.prompt,
            parameters={"aspect_ratio": args.aspect_ratio, "quality": args.quality},
        )
    )
    result = OpenAICodexNativeProvider().run_job(library_path, job.id)
    _print_json(result)
    return 0


def _require_isolated_experiment_library(library_path: Path) -> None:
    if library_path.exists() and any(library_path.iterdir()):
        raise ValueError("The 10-worker live experiment requires a new or empty isolated QA library")


def experiment_10(args: argparse.Namespace) -> int:
    """Run the approved 10-worker live experiment without changing product concurrency."""
    library_path = Path(args.library).expanduser()
    _require_isolated_experiment_library(library_path)
    repo = GenerationJobRepository(library_path)
    generation_set = repo.create_job_set(
        GenerationJobCreate(
            provider=PROVIDER_ID,
            model=IMAGE_MODEL,
            prompt_text=args.prompt,
            parameters={
                "requested_aspect_ratio": args.aspect_ratio,
                "quality": args.quality,
            },
        ),
        10,
    )
    lock = Lock()
    active = 0
    max_active = 0
    started = time.monotonic()

    def run(job_id: str) -> dict[str, Any]:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            OpenAICodexNativeProvider().run_job(library_path, job_id)
        except (CodexNativeAuthError, GenerationJobConflict, KeyError, OSError, ValueError):
            pass
        finally:
            with lock:
                active -= 1
        job = repo.get_job(job_id)
        return {
            "id": job.id,
            "status": job.status,
            "error_kind": job.metadata.get("error_kind"),
            "error": sanitize_generation_error(job.error) if job.error else None,
        }

    results = []
    with ThreadPoolExecutor(max_workers=10, thread_name_prefix="generation-live-experiment") as executor:
        futures = [executor.submit(run, job.id) for job in generation_set.jobs]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: result["id"])
    status_counts: dict[str, int] = {}
    for result in results:
        status = str(result["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    _print_json({
        "experiment": "10 concurrent live generation requests",
        "generation_group_id": generation_set.generation_group_id,
        "requested": 10,
        "worker_limit": 10,
        "max_observed_worker_concurrency": max_active,
        "duration_seconds": round(time.monotonic() - started, 2),
        "status_counts": status_counts,
        "jobs": results,
    })
    return 0 if status_counts == {"succeeded": 10} and max_active == 10 else 1


def _add_library_arg(parser: argparse.ArgumentParser, *, default: str | None = "library") -> None:
    kwargs: dict[str, Any] = {
        "help": "Path to the local Image Prompt Library data directory (default: ./library).",
    }
    if default is None:
        kwargs["default"] = argparse.SUPPRESS
    else:
        kwargs["default"] = default
    parser.add_argument("--library", **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke-test Image Prompt Library's optional native ChatGPT/Codex OAuth provider."
    )
    _add_library_arg(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Print redacted provider status.")
    _add_library_arg(status_parser, default=None)
    status_parser.set_defaults(func=status)

    start_parser = subparsers.add_parser("start", help="Start Codex device-code OAuth.")
    _add_library_arg(start_parser, default=None)
    start_parser.set_defaults(func=start)

    poll_parser = subparsers.add_parser("poll", help="Poll Codex device-code OAuth after approving in browser.")
    _add_library_arg(poll_parser, default=None)
    poll_parser.add_argument("--device-auth-id", required=True)
    poll_parser.add_argument("--user-code", required=True)
    poll_parser.set_defaults(func=poll)

    disconnect_parser = subparsers.add_parser("disconnect", help="Delete the app-owned Codex OAuth token store.")
    _add_library_arg(disconnect_parser, default=None)
    disconnect_parser.set_defaults(func=disconnect)

    generate_parser = subparsers.add_parser("generate", help="Create and run a live Codex generation job.")
    _add_library_arg(generate_parser, default=None)
    generate_parser.add_argument("--prompt", required=True)
    generate_parser.add_argument("--aspect-ratio", default="square")
    generate_parser.add_argument("--quality", default="high")
    generate_parser.set_defaults(func=generate)

    experiment_parser = subparsers.add_parser(
        "experiment-10",
        help="Run an opt-in QA experiment with 10 direct concurrent live generation requests.",
    )
    experiment_parser.add_argument(
        "--library",
        required=True,
        help="Path to an isolated QA library data directory.",
    )
    experiment_parser.add_argument("--prompt", required=True)
    experiment_parser.add_argument("--aspect-ratio", default="1:1")
    experiment_parser.add_argument("--quality", default="low")
    experiment_parser.add_argument(
        "--confirm-live",
        action="store_true",
        required=True,
        help="Required acknowledgement that this sends 10 live generation requests.",
    )
    experiment_parser.set_defaults(func=experiment_10)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_app_owned_paths(Path(args.library).expanduser())
        return int(args.func(args) or 0)
    except (CodexNativeAuthError, GenerationJobConflict, KeyError, OSError, ValueError) as exc:
        print(json.dumps({"error": sanitize_generation_error(str(exc))}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
