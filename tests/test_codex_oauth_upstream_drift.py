import json
import subprocess
import sys
from pathlib import Path


def write_upstream_fixture(root: Path, *, client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann") -> None:
    auth_dir = root / "codex-rs" / "login" / "src" / "auth"
    login_dir = root / "codex-rs" / "login" / "src"
    auth_dir.mkdir(parents=True)
    login_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "manager.rs").write_text(
        '\n'.join([
            'const REFRESH_TOKEN_URL: &str = "https://auth.openai.com/oauth/token";',
            f'pub const CLIENT_ID: &str = "{client_id}";',
        ]),
        encoding="utf-8",
    )
    (login_dir / "device_code_auth.rs").write_text(
        '\n'.join([
            'let url = format!("{auth_base_url}/deviceauth/usercode");',
            'let url = format!("{auth_base_url}/deviceauth/token");',
            'verification_url: format!("{base_url}/codex/device"),',
            'let redirect_uri = format!("{base_url}/deviceauth/callback");',
        ]),
        encoding="utf-8",
    )
    (login_dir / "server.rs").write_text(
        'const DEFAULT_ISSUER: &str = "https://auth.openai.com";\n'
        '.post(format!("{issuer}/oauth/token"))\n',
        encoding="utf-8",
    )


def run_check(upstream_dir: Path):
    return subprocess.run(
        [
            sys.executable,
            "scripts/check-codex-oauth-upstream.py",
            "--upstream-dir",
            str(upstream_dir),
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )


def test_codex_oauth_upstream_check_passes_when_fixture_matches_local_constants(tmp_path):
    upstream = tmp_path / "codex"
    write_upstream_fixture(upstream)

    result = run_check(upstream)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["local"]["client_id"] == "app_EMoamEEZ73f0CkXaXp7hrann"
    assert payload["upstream"]["client_id"] == payload["local"]["client_id"]
    assert payload["checks"]["client_id"]["ok"] is True
    assert payload["checks"]["device_usercode_suffix"]["ok"] is True
    assert payload["checks"]["device_token_suffix"]["ok"] is True
    assert payload["checks"]["token_url"]["ok"] is True


def test_codex_oauth_upstream_check_fails_on_client_id_drift(tmp_path):
    upstream = tmp_path / "codex"
    write_upstream_fixture(upstream, client_id="app_CHANGED_UPSTREAM")

    result = run_check(upstream)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["checks"]["client_id"]["ok"] is False
    assert payload["checks"]["client_id"]["local"] == "app_EMoamEEZ73f0CkXaXp7hrann"
    assert payload["checks"]["client_id"]["upstream"] == "app_CHANGED_UPSTREAM"


def test_codex_oauth_upstream_check_fails_on_missing_device_flow_contract(tmp_path):
    upstream = tmp_path / "codex"
    write_upstream_fixture(upstream)
    (upstream / "codex-rs" / "login" / "src" / "device_code_auth.rs").write_text(
        'let url = format!("{auth_base_url}/changed/usercode");\n',
        encoding="utf-8",
    )

    result = run_check(upstream)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["checks"]["device_usercode_suffix"]["ok"] is False
    assert payload["checks"]["device_token_suffix"]["ok"] is False
