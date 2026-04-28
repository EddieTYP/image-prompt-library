#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (CodexNativeAuthError, GenerationJobConflict, KeyError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
