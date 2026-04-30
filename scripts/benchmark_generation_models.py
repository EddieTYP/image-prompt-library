#!/usr/bin/env python3
"""Run sequential Image Prompt Library generation-model timing checks.

This intentionally runs one job at a time so model latency comparisons are not
confounded by the local queue or provider-side concurrency. It talks to a
running local backend; it does not read or print OAuth tokens.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx


@dataclass
class BenchmarkResult:
    orchestrator_model: str
    status: str
    job_id: str | None
    create_seconds: float
    run_seconds: float
    total_seconds: float
    result_width: int | None = None
    result_height: int | None = None
    error: str | None = None


def post_json(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response from {path}")
    return data


def run_one(client: httpx.Client, model: str, prompt: str, aspect: str, quality: str) -> BenchmarkResult:
    started = time.perf_counter()
    job_id: str | None = None
    try:
        create_started = time.perf_counter()
        job = post_json(client, "/api/generation-jobs", {
            "mode": "text_to_image",
            "provider": "openai_codex_oauth_native",
            "model": "gpt-image-2",
            "prompt_language": "en",
            "prompt_text": prompt,
            "reference_image_ids": [],
            "parameters": {
                "requested_aspect_ratio": aspect,
                "aspect_ratio_prompt_injection": True,
                "quality": quality,
                "orchestrator_model": model,
            },
        })
        create_seconds = time.perf_counter() - create_started
        job_id = str(job.get("id") or "") or None
        run_started = time.perf_counter()
        result = post_json(client, f"/api/generation-jobs/{job_id}/run", {})
        run_seconds = time.perf_counter() - run_started
        return BenchmarkResult(
            orchestrator_model=model,
            status=str(result.get("status") or "unknown"),
            job_id=job_id,
            create_seconds=round(create_seconds, 3),
            run_seconds=round(run_seconds, 3),
            total_seconds=round(time.perf_counter() - started, 3),
            result_width=result.get("result_width"),
            result_height=result.get("result_height"),
            error=result.get("error"),
        )
    except Exception as exc:
        return BenchmarkResult(
            orchestrator_model=model,
            status="error",
            job_id=job_id,
            create_seconds=0.0,
            run_seconds=0.0,
            total_seconds=round(time.perf_counter() - started, 3),
            error=str(exc),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sequentially benchmark configured ChatGPT/Codex image orchestrator models.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Backend base URL")
    parser.add_argument("--models", default="", help="Comma-separated orchestrator models. Defaults to provider API models.")
    parser.add_argument("--prompt", default="A small porcelain robot reading a book beside a rainy neon window.")
    parser.add_argument("--aspect", default="1:1")
    parser.add_argument("--quality", default="standard", choices=["standard", "high"])
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=httpx.Timeout(args.timeout)) as client:
        if args.models.strip():
            models = [part.strip() for part in args.models.split(",") if part.strip()]
        else:
            providers = client.get("/api/generation-providers").json()
            codex = next((provider for provider in providers if provider.get("provider") == "openai_codex_oauth_native"), {})
            models = [str(model) for model in codex.get("orchestrator_models", []) if str(model).strip()]
        if not models:
            raise SystemExit("No orchestrator models available from provider API or --models")
        results = [run_one(client, model, args.prompt, args.aspect, args.quality) for model in models]
    print(json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False))
    return 0 if all(result.status == "succeeded" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
