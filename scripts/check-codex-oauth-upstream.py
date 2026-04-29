#!/usr/bin/env python3
"""Check Image Prompt Library's native Codex OAuth assumptions against upstream openai/codex.

This is a release-safety/drift check for the experimental local-only
`openai_codex_oauth_native` provider. It compares the app's pinned/default
OAuth contract with the public OpenAI Codex CLI source and can optionally run a
no-token device-code smoke request.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.openai_codex_native import (  # noqa: E402
    CODEX_AUTH_ISSUER,
    CODEX_TOKEN_URL,
    DEFAULT_CODEX_CLIENT_ID,
)

UPSTREAM_RAW_BASE = "https://raw.githubusercontent.com/openai/codex/{ref}/{path}"
UPSTREAM_PATHS = {
    "manager": "codex-rs/login/src/auth/manager.rs",
    "device_code_auth": "codex-rs/login/src/device_code_auth.rs",
    "server": "codex-rs/login/src/server.rs",
}

EXPECTED_DEVICE_USERCODE_SUFFIX = "/deviceauth/usercode"
EXPECTED_DEVICE_TOKEN_SUFFIX = "/deviceauth/token"
EXPECTED_VERIFICATION_SUFFIX = "/codex/device"
EXPECTED_REDIRECT_SUFFIX = "/deviceauth/callback"


class DriftCheckError(RuntimeError):
    pass


def read_upstream_file(path: str, *, ref: str, upstream_dir: Path | None) -> str:
    if upstream_dir is not None:
        file_path = upstream_dir / path
        try:
            return file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DriftCheckError(f"Cannot read upstream fixture {file_path}: {exc}") from exc
    url = UPSTREAM_RAW_BASE.format(ref=ref, path=path)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return response.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - network failure shape depends on platform
        raise DriftCheckError(f"Cannot fetch {url}: {exc}") from exc


def require_regex(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text)
    if not match:
        raise DriftCheckError(f"Could not extract {label} from upstream source")
    return match.group(1)


def collect_upstream_contract(*, ref: str, upstream_dir: Path | None) -> dict[str, Any]:
    manager = read_upstream_file(UPSTREAM_PATHS["manager"], ref=ref, upstream_dir=upstream_dir)
    device = read_upstream_file(UPSTREAM_PATHS["device_code_auth"], ref=ref, upstream_dir=upstream_dir)
    server = read_upstream_file(UPSTREAM_PATHS["server"], ref=ref, upstream_dir=upstream_dir)

    client_id = require_regex(r'pub\s+const\s+CLIENT_ID\s*:\s*&str\s*=\s*"([^"]+)"', manager, "CLIENT_ID")
    token_url = require_regex(r'REFRESH_TOKEN_URL\s*:\s*&str\s*=\s*"([^"]+)"', manager, "REFRESH_TOKEN_URL")
    issuer = require_regex(r'DEFAULT_ISSUER\s*:\s*&str\s*=\s*"([^"]+)"', server, "DEFAULT_ISSUER")

    return {
        "source": "local fixture" if upstream_dir else "openai/codex",
        "ref": ref,
        "paths": UPSTREAM_PATHS,
        "client_id": client_id,
        "issuer": issuer,
        "token_url": token_url,
        "device_usercode_suffix_present": EXPECTED_DEVICE_USERCODE_SUFFIX in device,
        "device_token_suffix_present": EXPECTED_DEVICE_TOKEN_SUFFIX in device,
        "verification_suffix_present": EXPECTED_VERIFICATION_SUFFIX in device,
        "redirect_suffix_present": EXPECTED_REDIRECT_SUFFIX in device,
    }


def local_contract() -> dict[str, Any]:
    return {
        "client_id": DEFAULT_CODEX_CLIENT_ID,
        "issuer": CODEX_AUTH_ISSUER,
        "token_url": CODEX_TOKEN_URL,
        "device_usercode_endpoint": f"{CODEX_AUTH_ISSUER}/api/accounts{EXPECTED_DEVICE_USERCODE_SUFFIX}",
        "device_token_endpoint": f"{CODEX_AUTH_ISSUER}/api/accounts{EXPECTED_DEVICE_TOKEN_SUFFIX}",
        "verification_url": f"{CODEX_AUTH_ISSUER}{EXPECTED_VERIFICATION_SUFFIX}",
        "redirect_uri": f"{CODEX_AUTH_ISSUER}{EXPECTED_REDIRECT_SUFFIX}",
    }


def check_equal(name: str, local: Any, upstream: Any) -> dict[str, Any]:
    return {"ok": local == upstream, "local": local, "upstream": upstream}


def check_present(name: str, local_expected: str, upstream_present: bool) -> dict[str, Any]:
    return {"ok": bool(upstream_present), "local_expected": local_expected, "upstream_present": bool(upstream_present)}


def run_live_device_smoke(client_id: str) -> dict[str, Any]:
    import httpx

    endpoint = f"{CODEX_AUTH_ISSUER}/api/accounts{EXPECTED_DEVICE_USERCODE_SUFFIX}"
    try:
        response = httpx.post(
            endpoint,
            json={"client_id": client_id},
            headers={"Content-Type": "application/json"},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "endpoint": endpoint, "error": str(exc)}
    payload: dict[str, Any]
    try:
        parsed = response.json()
        payload = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        payload = {}
    expected_fields = ["user_code", "device_auth_id", "interval"]
    missing = [field for field in expected_fields if not payload.get(field)]
    return {
        "ok": response.status_code == 200 and not missing,
        "endpoint": endpoint,
        "status_code": response.status_code,
        "missing_fields": missing,
        "has_user_code": bool(payload.get("user_code")),
        "has_device_auth_id": bool(payload.get("device_auth_id")),
        "interval": payload.get("interval"),
        "verification_url": f"{CODEX_AUTH_ISSUER}{EXPECTED_VERIFICATION_SUFFIX}",
    }


def build_report(*, ref: str, upstream_dir: Path | None, live_device_smoke: bool) -> dict[str, Any]:
    local = local_contract()
    upstream = collect_upstream_contract(ref=ref, upstream_dir=upstream_dir)
    checks = {
        "client_id": check_equal("client_id", local["client_id"], upstream["client_id"]),
        "issuer": check_equal("issuer", local["issuer"], upstream["issuer"]),
        "token_url": check_equal("token_url", local["token_url"], upstream["token_url"]),
        "device_usercode_suffix": check_present(
            "device_usercode_suffix",
            EXPECTED_DEVICE_USERCODE_SUFFIX,
            upstream["device_usercode_suffix_present"],
        ),
        "device_token_suffix": check_present(
            "device_token_suffix",
            EXPECTED_DEVICE_TOKEN_SUFFIX,
            upstream["device_token_suffix_present"],
        ),
        "verification_suffix": check_present(
            "verification_suffix",
            EXPECTED_VERIFICATION_SUFFIX,
            upstream["verification_suffix_present"],
        ),
        "redirect_suffix": check_present(
            "redirect_suffix",
            EXPECTED_REDIRECT_SUFFIX,
            upstream["redirect_suffix_present"],
        ),
    }
    if live_device_smoke:
        checks["live_device_smoke"] = run_live_device_smoke(local["client_id"])
    ok = all(bool(check.get("ok")) for check in checks.values())
    return {"ok": ok, "local": local, "upstream": upstream, "checks": checks}


def format_human(report: dict[str, Any]) -> str:
    lines = [
        "Codex OAuth upstream drift check",
        f"overall: {'OK' if report['ok'] else 'DRIFT DETECTED'}",
        f"upstream: {report['upstream']['source']} @ {report['upstream']['ref']}",
        "",
    ]
    for name, check in report["checks"].items():
        lines.append(f"- {name}: {'OK' if check.get('ok') else 'FAIL'}")
        if not check.get("ok"):
            for key, value in check.items():
                if key != "ok":
                    lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="openai/codex git ref to inspect (default: main)")
    parser.add_argument("--upstream-dir", type=Path, help="local openai/codex checkout or fixture root")
    parser.add_argument("--live-device-smoke", action="store_true", help="also call the live no-token device-code endpoint")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = build_report(ref=args.ref, upstream_dir=args.upstream_dir, live_device_smoke=args.live_device_smoke)
    except DriftCheckError as exc:
        report = {"ok": False, "error": str(exc)}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_human(report) if "checks" in report else f"Codex OAuth upstream drift check\noverall: FAIL\nerror: {report['error']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
