import base64
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.db import connect
from backend.main import create_app


def png_bytes(color="purple", size=(16, 10)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def fake_jwt(account_id="acct_test_123", exp=4_102_444_800) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
        "exp": exp,
    }).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def create_source_item(c):
    return c.post("/api/items", json={
        "title": "Codex source prompt",
        "prompts": [{"language": "en", "text": "A neon library in the rain", "is_original": True}],
    }).json()


def test_codex_native_token_store_is_app_owned_redacted_and_permissioned(tmp_path, monkeypatch):
    auth_path = tmp_path / "app-auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))

    from backend.services.openai_codex_native import CodexNativeAuthStore, codex_cloudflare_headers

    store = CodexNativeAuthStore()
    assert store.path == auth_path
    assert "library" not in str(store.path)
    assert store.status()["available"] is False

    store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})

    raw = json.loads(auth_path.read_text())
    assert raw["provider"] == "openai_codex_oauth_native"
    assert raw["auth_mode"] == "codex_oauth_native"
    assert raw["tokens"]["access_token"].startswith("ey")
    if os.name != "nt":
        assert oct(auth_path.stat().st_mode & 0o777) == "0o600"

    status = store.status()
    assert status["provider"] == "openai_codex_oauth_native"
    assert status["auth_mode"] == "codex_oauth_native"
    assert status["optional"] is True
    assert status["authenticated"] is True
    assert status["token_present"] is True
    assert status["account_id"] == "acct_test_123"
    assert status["auth_store_path"] == str(auth_path)
    assert "refresh-secret" not in json.dumps(status)
    assert "access_token" not in status
    assert codex_cloudflare_headers(fake_jwt())["ChatGPT-Account-ID"] == "acct_test_123"


def test_codex_native_status_api_is_optional_frontend_ready_and_redacted(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth-outside-library" / "auth.json"
    config_path = tmp_path / "missing-config.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", raising=False)
    c = client(tmp_path)

    response = c.get("/api/generation-providers/openai-codex-native/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai_codex_oauth_native"
    assert payload["display_name"] == "ChatGPT / Codex OAuth"
    assert payload["optional"] is True
    assert payload["configured"] is True
    assert payload["authenticated"] is False
    assert payload["available"] is False
    assert payload["state"] == "not_connected"
    assert payload["reason"] == "not_authenticated"
    assert payload["features"] == {
        "text_to_image": False,
        "text_reference_to_image": False,
        "image_edit": False,
    }
    assert payload["auth_store_path"] == str(auth_path)
    assert str(tmp_path / "library") not in payload["auth_store_path"]
    assert "token" not in json.dumps(payload).lower().replace("token_present", "")


def test_codex_native_status_uses_local_config_client_id_and_lists_optional_providers(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    config_path = tmp_path / "config" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({
        "providers": {
            "openai_codex_oauth_native": {"client_id": "config-client-id"}
        }
    }), encoding="utf-8")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", raising=False)

    c = client(tmp_path)
    status = c.get("/api/generation-providers/openai-codex-native/status").json()
    assert status["configured"] is True
    assert status["authenticated"] is False
    assert status["available"] is False
    assert status["state"] == "not_connected"
    assert status["reason"] == "not_authenticated"
    assert status["features"]["text_to_image"] is False

    providers = c.get("/api/generation-providers").json()
    assert providers[0]["provider"] == "manual_upload"
    codex = next(provider for provider in providers if provider["provider"] == "openai_codex_oauth_native")
    assert codex["optional"] is True
    assert codex["state"] == "not_connected"
    xai = next(provider for provider in providers if provider["provider"] == "xai_api")
    assert xai["optional"] is True
    assert xai["state"] == "not_configured"
    assert xai["default_image_model"] == "grok-imagine-image-2.0"


def test_codex_native_disconnect_removes_only_app_auth_store(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    assert auth_path.exists()

    c = client(tmp_path)
    response = c.post("/api/generation-providers/openai-codex-native/auth/disconnect")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "not_connected"
    assert payload["configured"] is True
    assert payload["authenticated"] is False
    assert auth_path.exists() is False


def test_codex_native_smoke_parser_preserves_global_library_argument():
    from scripts.codex_native_oauth_smoke import build_parser

    args = build_parser().parse_args(["--library", ".local-work/smoke", "generate", "--prompt", "hello"])
    assert args.library == ".local-work/smoke"

    args = build_parser().parse_args(["generate", "--library", ".local-work/smoke", "--prompt", "hello"])
    assert args.library == ".local-work/smoke"


def test_codex_native_live_experiment_requires_explicit_opt_in_and_library():
    from scripts.codex_native_oauth_smoke import build_parser, experiment_10

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["experiment-10", "--prompt", "hello", "--confirm-live"])
    with pytest.raises(SystemExit):
        parser.parse_args(["experiment-10", "--library", ".local-work/live", "--prompt", "hello"])

    args = parser.parse_args([
        "experiment-10",
        "--library",
        ".local-work/live",
        "--prompt",
        "hello",
        "--confirm-live",
    ])
    assert args.func is experiment_10
    assert args.library == ".local-work/live"
    assert args.quality == "low"


def test_codex_native_live_experiment_rejects_nonempty_library(tmp_path):
    from scripts.codex_native_oauth_smoke import _require_isolated_experiment_library

    library = tmp_path / "active-library"
    library.mkdir()
    canary = library / "keep.txt"
    canary.write_text("user data", encoding="utf-8")
    with pytest.raises(ValueError, match="new or empty isolated QA library"):
        _require_isolated_experiment_library(library)
    assert canary.read_text(encoding="utf-8") == "user data"


def test_codex_native_smoke_script_reports_optional_status_without_tokens(tmp_path):
    auth_path = tmp_path / "auth" / "auth.json"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_AUTH_PATH"] = str(auth_path)
    env["IMAGE_PROMPT_LIBRARY_CONFIG_PATH"] = str(tmp_path / "missing-config.json")
    env.pop("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", None)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/codex_native_oauth_smoke.py",
            "status",
            "--library",
            str(tmp_path / "library"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "not_connected"
    assert payload["available"] is False
    assert "access_token" not in result.stdout


def test_codex_native_smoke_rejects_unsafe_auth_path_before_reading_library(tmp_path):
    library = tmp_path / "library"
    unsafe_auth = library / "originals" / "auth.json"
    unsafe_auth.parent.mkdir(parents=True)
    unsafe_auth.write_text("smoke-auth-canary", encoding="utf-8")
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_AUTH_PATH"] = str(unsafe_auth)
    env["IMAGE_PROMPT_LIBRARY_CONFIG_PATH"] = str(tmp_path / "app-state" / "config.json")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/codex_native_oauth_smoke.py",
            "status",
            "--library",
            str(library),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "IMAGE_PROMPT_LIBRARY_AUTH_PATH" in result.stderr
    assert "smoke-auth-canary" not in result.stderr
    assert unsafe_auth.read_text(encoding="utf-8") == "smoke-auth-canary"
    assert not (library / "db.sqlite").exists()


def test_codex_native_provider_rejects_unsafe_path_before_repository_initialization(tmp_path, monkeypatch):
    from backend.services.openai_codex_native import CodexNativeAuthError, OpenAICodexNativeProvider

    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(library / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))

    with pytest.raises(CodexNativeAuthError, match="Provider credentials or library storage paths are unsafe"):
        OpenAICodexNativeProvider().run_job(library, "missing-job")

    assert not (library / "db.sqlite").exists()


def test_codex_native_provider_marks_existing_job_failed_when_runtime_boundary_becomes_unsafe(tmp_path, monkeypatch):
    from backend.schemas import GenerationJobCreate
    from backend.services.generation_jobs import GenerationJobRepository
    from backend.services.openai_codex_native import CodexNativeAuthError, OpenAICodexNativeProvider

    library = tmp_path / "library"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(tmp_path / "app-state" / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider="openai_codex_oauth_native", prompt_text="boundary failure"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(library / "auth.json"))

    with pytest.raises(CodexNativeAuthError, match="Provider credentials or library storage paths are unsafe"):
        OpenAICodexNativeProvider().run_job(library, job.id)

    failed = repo.get_job(job.id)
    assert failed.status == "failed"
    assert failed.started_at is not None
    assert failed.metadata["error_kind"] == "auth_required"
    assert str(library) not in (failed.error or "")


def test_codex_native_refreshes_expired_access_token_before_use(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services.openai_codex_native import CodexNativeAuthStore

    seen_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_bodies.append(request.content.decode())
        return httpx.Response(200, json={
            "access_token": fake_jwt("acct_refreshed"),
            "refresh_token": "refresh-token-rotated",
        })

    store = CodexNativeAuthStore()
    store.save_tokens({"access_token": fake_jwt("acct_expired", exp=1), "refresh_token": "refresh-token-old"})
    tokens = store.read_tokens(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert tokens["access_token"] == fake_jwt("acct_refreshed")
    assert tokens["refresh_token"] == "refresh-token-rotated"
    assert "grant_type=refresh_token" in seen_bodies[0]
    assert "client_id=codex-client-test" in seen_bodies[0]
    assert "refresh-token-rotated" in auth_path.read_text()


@pytest.mark.parametrize("failure", ["network", "request_timeout", "server"])
def test_codex_native_refresh_maps_transient_failures_to_temporary_error(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ReadTimeout("timed out", request=request)
        if failure == "request_timeout":
            return httpx.Response(408)
        return httpx.Response(503)

    auth_path = tmp_path / "auth" / "auth.json"
    store = CodexNativeAuthStore(auth_path)
    store.save_tokens({"access_token": fake_jwt(exp=1), "refresh_token": "refresh-secret"})
    saved_credentials = auth_path.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(CodexNativeTemporaryError) as error:
            store.refresh_tokens("refresh-secret", http_client=http_client)
    assert str(error.value) == "Token refresh is temporarily unavailable"
    assert auth_path.read_bytes() == saved_credentials


@pytest.mark.parametrize("status_code", [400, 401, 403])
def test_codex_native_refresh_keeps_oauth_credential_failures_as_auth_errors(tmp_path, monkeypatch, status_code):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services.openai_codex_native import (
        CodexNativeAuthError,
        CodexNativeAuthStore,
        CodexNativeTemporaryError,
    )

    store = CodexNativeAuthStore(tmp_path / "auth.json")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status_code))) as http_client:
        with pytest.raises(CodexNativeAuthError) as error:
            store.refresh_tokens("refresh-secret", http_client=http_client)

    assert not isinstance(error.value, CodexNativeTemporaryError)


def test_codex_native_malformed_local_credentials_raise_auth_error(tmp_path):
    from backend.services.openai_codex_native import CodexNativeAuthError, CodexNativeAuthStore

    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{", encoding="utf-8")

    with pytest.raises(CodexNativeAuthError):
        CodexNativeAuthStore(auth_path).read_tokens()


def test_codex_native_invalid_utf8_credentials_raise_auth_error(tmp_path):
    from backend.services.openai_codex_native import CodexNativeAuthError, CodexNativeAuthStore

    auth_path = tmp_path / "auth.json"
    auth_path.write_bytes(b"\xff")

    with pytest.raises(CodexNativeAuthError):
        CodexNativeAuthStore(auth_path).read_tokens()


@pytest.mark.parametrize("tokens", [
    {"access_token": 123, "refresh_token": "refresh-secret"},
    {"access_token": fake_jwt(), "refresh_token": ["refresh-secret"]},
])
def test_codex_native_non_string_token_values_raise_auth_error(tmp_path, tokens):
    from backend.services.openai_codex_native import CodexNativeAuthError, CodexNativeAuthStore

    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"tokens": tokens}), encoding="utf-8")

    with pytest.raises(CodexNativeAuthError):
        CodexNativeAuthStore(auth_path).read_tokens()


def test_codex_native_refresh_coordinates_independent_processes(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    second_refresh_started_path = tmp_path / "second-refresh-started"
    refreshed_access_token = fake_jwt("acct_refreshed")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore(auth_path).save_tokens({
        "access_token": fake_jwt("acct_expired", exp=1),
        "refresh_token": "refresh-token-old",
    })

    first_request = threading.Event()
    release_first_response = threading.Event()
    request_lock = threading.Lock()
    refresh_requests = 0

    class TokenHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal refresh_requests
            with request_lock:
                refresh_requests += 1
                request_number = refresh_requests
            if request_number == 1:
                first_request.set()
                assert release_first_response.wait(timeout=10)
            body = json.dumps({
                "access_token": refreshed_access_token,
                "refresh_token": "refresh-token-rotated",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), TokenHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    token_url = f"http://127.0.0.1:{server.server_port}/oauth/token"
    worker = "\n".join([
        "import json",
        "import sys",
        "from pathlib import Path",
        "from backend.services import openai_codex_native",
        "openai_codex_native.CODEX_TOKEN_URL = sys.argv[2]",
        "if len(sys.argv) == 4:",
        "    expires_soon = openai_codex_native._token_expires_soon",
        "    def signal_refresh_start(token, skew_seconds=300):",
        "        Path(sys.argv[3]).write_text('started', encoding='utf-8')",
        "        return expires_soon(token, skew_seconds)",
        "    openai_codex_native._token_expires_soon = signal_refresh_start",
        "tokens = openai_codex_native.CodexNativeAuthStore(Path(sys.argv[1])).read_tokens()",
        "print(json.dumps(tokens))",
    ])

    first = None
    second = None
    workers_completed = False
    try:
        first = subprocess.Popen(
            [sys.executable, "-c", worker, str(auth_path), token_url],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert first_request.wait(timeout=10)

        second = subprocess.Popen(
            [sys.executable, "-c", worker, str(auth_path), token_url, str(second_refresh_started_path)],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while not second_refresh_started_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert second_refresh_started_path.exists()
        release_first_response.set()

        first_stdout, first_stderr = first.communicate(timeout=10)
        second_stdout, second_stderr = second.communicate(timeout=10)
        workers_completed = True
    finally:
        release_first_response.set()
        if not workers_completed:
            for worker_process in (first, second):
                if worker_process is None:
                    continue
                if worker_process.poll() is None:
                    worker_process.terminate()
                try:
                    worker_process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    worker_process.kill()
                    worker_process.communicate(timeout=5)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=10)

    assert first.returncode == 0, first_stderr
    assert second.returncode == 0, second_stderr
    first_result = json.loads(first_stdout)
    second_result = json.loads(second_stdout)
    assert refresh_requests == 1
    assert first_result["access_token"] == refreshed_access_token
    assert second_result["access_token"] == refreshed_access_token


def _start_codex_lock_holder(auth_path, ready_path):
    worker = "\n".join([
        "import time",
        "import sys",
        "from pathlib import Path",
        "from backend.services.openai_codex_native import CodexNativeAuthStore",
        "with CodexNativeAuthStore(Path(sys.argv[1]))._refresh_lock():",
        "    Path(sys.argv[2]).write_text('ready', encoding='utf-8')",
        "    time.sleep(60)",
    ])
    process = subprocess.Popen(
        [sys.executable, "-c", worker, str(auth_path), str(ready_path)],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    if ready_path.exists():
        return process
    if process.poll() is None:
        process.terminate()
    _, stderr = process.communicate(timeout=5)
    raise AssertionError(stderr or "Lock holder did not become ready")


def test_codex_native_refresh_lock_releases_when_owner_is_killed(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    ready_path = tmp_path / "lock-ready"

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    store = CodexNativeAuthStore(auth_path)
    store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})
    process = _start_codex_lock_holder(auth_path, ready_path)
    try:
        process.kill()
        process.communicate(timeout=5)
        monkeypatch.setattr(openai_codex_native, "AUTH_REFRESH_LOCK_WAIT_SECONDS", 1.0)

        with store._refresh_lock():
            assert auth_path.with_name(f"{auth_path.name}.refresh.lock").is_file()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)

    assert auth_path.with_name(f"{auth_path.name}.refresh.lock").is_file()


def test_codex_native_refresh_lock_open_failure_is_temporary_and_redacted(tmp_path, monkeypatch):
    auth_path = tmp_path / "private-auth" / "auth.json"
    lock_path = auth_path.with_name(f"{auth_path.name}.refresh.lock")

    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    store = CodexNativeAuthStore(auth_path)
    original_open = Path.open

    def fail_open(self, *args, **kwargs):
        if self == lock_path:
            raise OSError(f"permission denied: {lock_path}")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(CodexNativeTemporaryError) as error:
        with store._refresh_lock():
            pass

    assert str(error.value) == "Token refresh is temporarily unavailable"
    assert str(lock_path) not in str(error.value)


def test_codex_native_refresh_lock_wait_is_bounded_and_temporary(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    ready_path = tmp_path / "lock-ready"

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    store = CodexNativeAuthStore(auth_path)
    store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})
    process = _start_codex_lock_holder(auth_path, ready_path)
    try:
        assert openai_codex_native.AUTH_REFRESH_LOCK_POLL_SECONDS == 0.1
        assert openai_codex_native.AUTH_REFRESH_LOCK_WAIT_SECONDS == 20.0
        assert not hasattr(openai_codex_native, "AUTH_REFRESH_LOCK_STALE_SECONDS")
        monkeypatch.setattr(openai_codex_native, "AUTH_REFRESH_LOCK_WAIT_SECONDS", 0.25)
        started = time.monotonic()
        with pytest.raises(CodexNativeTemporaryError):
            with store._refresh_lock():
                pass
        elapsed = time.monotonic() - started

        assert 0.2 <= elapsed < 2.0
        lock_path = auth_path.with_name(f"{auth_path.name}.refresh.lock")
        assert lock_path.is_file()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_codex_native_lock_timeout_returns_fresh_tokens_written_at_deadline(tmp_path, monkeypatch):
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    store = CodexNativeAuthStore(tmp_path / "auth.json")
    expired = {"access_token": fake_jwt(exp=1), "refresh_token": "refresh-secret"}
    refreshed = {"access_token": fake_jwt(exp=4_102_444_800), "refresh_token": "refresh-token-rotated"}
    reads = iter([expired, refreshed])

    @contextmanager
    def timed_out_lock():
        raise CodexNativeTemporaryError("Token refresh is temporarily unavailable")
        yield

    monkeypatch.setattr(store, "_read_raw_tokens", lambda: next(reads))
    monkeypatch.setattr(store, "_refresh_lock", timed_out_lock)

    assert store.read_tokens() == refreshed


def test_codex_native_refresh_lock_never_retries_after_its_deadline(tmp_path, monkeypatch):
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    store = CodexNativeAuthStore(tmp_path / "auth.json")
    clock = [0.0]
    sleep_calls = []
    attempts = []

    def sleep(seconds):
        sleep_calls.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(openai_codex_native, "AUTH_REFRESH_LOCK_WAIT_SECONDS", 0.25)
    monkeypatch.setattr(openai_codex_native.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(openai_codex_native.time, "sleep", sleep)
    monkeypatch.setattr(openai_codex_native, "_try_lock_file", lambda lock_file: attempts.append(1) and False)

    with pytest.raises(CodexNativeTemporaryError):
        with store._refresh_lock():
            pass

    assert len(attempts) == 3
    assert sleep_calls == pytest.approx([0.1, 0.1, 0.05])


def test_codex_native_refresh_lock_raises_temporary_error_when_deadline_passes_during_acquire(tmp_path, monkeypatch):
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    store = CodexNativeAuthStore(tmp_path / "auth.json")
    clock = [0.0]
    sleep_calls = []

    def failed_acquire(lock_file):
        clock[0] = 0.3
        return False

    monkeypatch.setattr(openai_codex_native, "AUTH_REFRESH_LOCK_WAIT_SECONDS", 0.25)
    monkeypatch.setattr(openai_codex_native.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(openai_codex_native.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(openai_codex_native, "_try_lock_file", failed_acquire)

    with pytest.raises(CodexNativeTemporaryError):
        with store._refresh_lock():
            pass

    assert sleep_calls == []


def test_codex_native_lock_timeout_preserves_temporary_error_when_final_reread_is_invalid(tmp_path, monkeypatch):
    from backend.services.openai_codex_native import CodexNativeAuthError, CodexNativeAuthStore, CodexNativeTemporaryError

    store = CodexNativeAuthStore(tmp_path / "auth.json")
    reads = iter([
        {"access_token": fake_jwt(exp=1), "refresh_token": "refresh-secret"},
        CodexNativeAuthError("Native Codex auth store has invalid token values"),
    ])

    @contextmanager
    def timed_out_lock():
        raise CodexNativeTemporaryError("Token refresh is temporarily unavailable")
        yield

    def read_tokens():
        value = next(reads)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(store, "_read_raw_tokens", read_tokens)
    monkeypatch.setattr(store, "_refresh_lock", timed_out_lock)

    with pytest.raises(CodexNativeTemporaryError):
        store.read_tokens()


def test_codex_native_device_flow_uses_codex_endpoints_and_saves_app_owned_tokens(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services.openai_codex_native import CodexDeviceCodeFlow, CodexNativeAuthStore

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), request.content.decode()))
        if str(request.url).endswith("/api/accounts/deviceauth/usercode"):
            return httpx.Response(200, json={
                "user_code": "ABCD-EFGH",
                "device_auth_id": "dev-auth-1",
                "interval": 3,
            })
        if str(request.url).endswith("/oauth/token"):
            return httpx.Response(200, json={
                "access_token": fake_jwt("acct_device_flow"),
                "refresh_token": "refresh-from-device-flow",
            })
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    flow = CodexDeviceCodeFlow(auth_store=CodexNativeAuthStore(), http_client=client)

    start = flow.start()
    assert start["user_code"] == "ABCD-EFGH"
    assert start["verification_url"] == "https://auth.openai.com/codex/device"
    assert start["device_auth_id"] == "dev-auth-1"
    assert auth_path.exists() is False

    status = flow.exchange_authorization_code("authorization-code", "verifier")
    assert status["available"] is True
    assert status["account_id"] == "acct_device_flow"
    assert auth_path.is_file()
    assert "refresh-from-device-flow" in auth_path.read_text()
    assert any("grant_type=authorization_code" in body for _, _, body in seen)
    assert any("client_id=codex-client-test" in body for _, _, body in seen)


def test_codex_native_device_flow_rejects_invalid_upstream_json(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services.openai_codex_native import CodexDeviceCodeFlow, CodexNativeAuthError, CodexNativeAuthStore

    def invalid_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    flow = CodexDeviceCodeFlow(
        auth_store=CodexNativeAuthStore(),
        http_client=httpx.Client(transport=httpx.MockTransport(invalid_json_handler)),
    )

    try:
        flow.start()
    except CodexNativeAuthError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("expected invalid JSON to be converted to CodexNativeAuthError")

    def invalid_interval_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "user_code": "ABCD-EFGH",
            "device_auth_id": "dev-auth-1",
            "interval": "not-an-int",
        })

    flow = CodexDeviceCodeFlow(
        auth_store=CodexNativeAuthStore(),
        http_client=httpx.Client(transport=httpx.MockTransport(invalid_interval_handler)),
    )
    try:
        flow.start()
    except CodexNativeAuthError as exc:
        assert "invalid interval" in str(exc)
    else:
        raise AssertionError("expected invalid interval to be converted to CodexNativeAuthError")


def test_codex_native_uses_verified_default_image_orchestration_models():
    from backend.services.openai_codex_native import CODEX_CHAT_MODEL, DEFAULT_CODEX_ORCHESTRATOR_MODELS, codex_orchestrator_models

    assert CODEX_CHAT_MODEL == "gpt-5.6-terra"
    assert DEFAULT_CODEX_ORCHESTRATOR_MODELS == ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"]
    assert codex_orchestrator_models() == ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"]


def test_codex_native_filters_known_text_only_orchestrator_models_from_env(monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_ORCHESTRATOR_MODELS", "gpt-5.5,gpt-5.3-codex-spark,gpt-5.3,gpt-5.4")

    from backend.services.openai_codex_native import codex_orchestrator_models

    assert codex_orchestrator_models() == ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4"]


def test_codex_native_status_exposes_orchestrator_and_image_models(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_ORCHESTRATOR_MODELS", "gpt-5.5,gpt-5.3-codex-spark")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    c = client(tmp_path)

    codex = next(provider for provider in c.get("/api/generation-providers").json() if provider["provider"] == "openai_codex_oauth_native")

    assert codex["orchestrator_models"] == ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.5"]
    assert codex["default_orchestrator_model"] == "gpt-5.6-terra"
    assert codex["image_models"] == ["gpt-image-2"]
    assert codex["default_image_model"] == "gpt-image-2"


def test_codex_native_status_exposes_generation_readiness_fields(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})
    payload = client(tmp_path).get("/api/generation-providers/openai-codex-native/status").json()

    assert payload["status"] == "ready"
    assert payload["can_generate"] is True
    assert payload["message"] is None


def test_codex_native_missing_login_maps_to_login_required(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    payload = client(tmp_path).get("/api/generation-providers/openai-codex-native/status").json()

    assert payload["status"] == "login_required"
    assert payload["can_generate"] is False
    assert payload["message"] == "Connect ChatGPT / Codex OAuth before generating."


def test_codex_native_broken_saved_login_maps_to_auth_error(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthError, CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(exp=1), "refresh_token": "refresh-secret"})
    monkeypatch.setattr(
        openai_codex_native.CodexNativeAuthStore,
        "refresh_tokens",
        lambda self, refresh_token, http_client=None: (_ for _ in ()).throw(
            CodexNativeAuthError("refresh-secret should stay private")
        ),
    )

    payload = client(tmp_path).get("/api/generation-providers/openai-codex-native/status").json()

    assert payload["state"] == "not_connected"
    assert payload["authenticated"] is False
    assert payload["reason"] == "not_authenticated"
    assert payload["status"] == "auth_error"
    assert payload["can_generate"] is False
    assert payload["message"] == "ChatGPT / Codex OAuth needs attention before generating."
    assert "refresh-secret" not in json.dumps(payload)
    assert str(auth_path.with_name(f"{auth_path.name}.refresh.lock")) not in json.dumps(payload)


def test_codex_native_temporary_refresh_failure_remains_connected_and_redacted(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(exp=1), "refresh_token": "refresh-secret"})
    temporary_error = getattr(openai_codex_native, "CodexNativeTemporaryError", httpx.ReadTimeout)
    monkeypatch.setattr(
        openai_codex_native.CodexNativeAuthStore,
        "refresh_tokens",
        lambda self, refresh_token, http_client=None: (_ for _ in ()).throw(
            temporary_error("refresh-secret should stay private")
        ),
    )

    payload = client(tmp_path).get("/api/generation-providers/openai-codex-native/status").json()

    assert payload["authenticated"] is True
    assert payload["state"] == "connected"
    assert payload["available"] is False
    assert payload["status"] == "unavailable"
    assert payload["message"] == "ChatGPT / Codex OAuth is temporarily unavailable. Try again shortly."
    assert "refresh-secret" not in json.dumps(payload)
    assert str(auth_path.with_name(f"{auth_path.name}.refresh.lock")) not in json.dumps(payload)


def test_codex_native_lock_open_failure_stays_unavailable_and_redacted(tmp_path, monkeypatch):
    auth_path = tmp_path / "private-auth" / "auth.json"
    lock_path = auth_path.with_name(f"{auth_path.name}.refresh.lock")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(exp=1), "refresh_token": "refresh-secret"})

    @contextmanager
    def lock_open_failure(self):
        raise CodexNativeTemporaryError("Token refresh is temporarily unavailable")
        yield

    monkeypatch.setattr(CodexNativeAuthStore, "_refresh_lock", lock_open_failure)
    c = client(tmp_path)
    status = c.get("/api/generation-providers/openai-codex-native/status").json()

    assert status["state"] == "connected"
    assert status["status"] == "unavailable"
    assert str(lock_path) not in json.dumps(status)

    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 409

    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["metadata"]["error_kind"] == "provider_unavailable"
    assert str(lock_path) not in json.dumps(failed)
    assert "refresh-secret" not in json.dumps(failed)


def test_generation_providers_manual_upload_is_always_generation_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")
    providers = client(tmp_path).get("/api/generation-providers").json()
    manual = providers[0]

    assert manual["provider"] == "manual_upload"
    assert manual["status"] == "ready"
    assert manual["can_generate"] is True
    assert manual["message"] is None


def test_codex_native_run_executes_job_and_stages_result_without_leaking_tokens(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})
    monkeypatch.setattr(
        openai_codex_native.OpenAICodexNativeProvider,
        "_collect_image_b64",
            lambda self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None: base64.b64encode(png_bytes()).decode(),
    )

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
        "parameters": {"aspect_ratio": "square", "quality": "high"},
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["provider"] == "openai_codex_oauth_native"
    assert payload["result_path"].startswith(f"generation-results/{job['id']}/")
    assert (tmp_path / "library" / payload["result_path"]).is_file()
    assert payload["metadata"]["provider"] == "openai_codex_oauth_native"
    assert payload["metadata"]["auth_mode"] == "codex_oauth_native"
    assert payload["metadata"]["model"] == "gpt-image-2"
    assert payload["result_width"] == 16
    assert payload["result_height"] == 10
    dumped = json.dumps(payload)
    assert "refresh-secret" not in dumped
    assert fake_jwt() not in dumped


def test_codex_native_injects_requested_aspect_ratio_and_records_effective_prompt(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    captured = {}

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        captured["prompt"] = prompt
        captured["size"] = size
        captured["quality"] = quality
        captured["image_model"] = image_model
        captured["orchestrator_model"] = orchestrator_model
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
        "parameters": {"requested_aspect_ratio": "4:3", "aspect_ratio_prompt_injection": True},
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 200
    payload = response.json()
    assert captured == {
        "prompt": "A neon library in the rain\n\nMake the aspect ratio 4:3.",
        "size": None,
        "quality": "high",
        "image_model": "gpt-image-2",
        "orchestrator_model": "gpt-5.6-terra",
    }
    assert payload["metadata"]["requested_aspect_ratio"] == "4:3"
    assert payload["metadata"]["aspect_ratio_prompt_injection"] == "Make the aspect ratio 4:3."
    assert payload["metadata"]["effective_prompt"] == captured["prompt"]
    assert payload["metadata"]["size"] == "auto"
    assert payload["metadata"]["native_size_parameter"] is None


def test_codex_native_auto_aspect_ratio_does_not_inject_instruction_or_size(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    captured = {}

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        captured["prompt"] = prompt
        captured["size"] = size
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A cinematic city that chooses its own frame",
        "parameters": {"requested_aspect_ratio": "auto", "aspect_ratio_prompt_injection": False},
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 200
    payload = response.json()
    assert captured == {"prompt": "A cinematic city that chooses its own frame", "size": None}
    assert payload["metadata"]["requested_aspect_ratio"] == "auto"
    assert payload["metadata"]["aspect_ratio_prompt_injection"] is None
    assert payload["metadata"]["effective_prompt"] == captured["prompt"]
    assert payload["metadata"]["size"] == "auto"
    assert payload["metadata"]["native_size_parameter"] is None


def test_codex_native_maps_standard_ui_quality_to_sdk_medium(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    captured = {}

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        captured["quality"] = quality
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
        "parameters": {"quality": "standard"},
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 200
    assert captured["quality"] == "medium"
    assert response.json()["metadata"]["quality"] == "medium"


def test_codex_native_forwards_up_to_four_edit_input_images(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    captured = {}
    image_data_url = "data:image/png;base64," + base64.b64encode(png_bytes()).decode()

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        captured["input_images"] = input_images
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "image_edit",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "Make this more painterly",
        "parameters": {"input_images": [{"source": "uploaded", "name": f"ref-{idx}.png", "data_url": image_data_url} for idx in range(4)]},
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 200
    assert len(captured["input_images"]) == 4
    assert all(image["image_url"].startswith("data:image/png;base64,") for image in captured["input_images"])
    assert response.json()["metadata"]["input_image_count"] == 4


def test_codex_native_preserves_mixed_library_and_upload_input_order(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    captured = {}

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        captured["input_images"] = input_images
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)
    c = client(tmp_path)
    source_item = create_source_item(c)
    library_image = c.post(
        f"/api/items/{source_item['id']}/images",
        files={"file": ("library.png", png_bytes("purple"), "image/png")},
        data={"role": "reference_image"},
    ).json()
    upload_data_url = "data:image/png;base64," + base64.b64encode(png_bytes("orange")).decode()
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "image_edit",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "Keep the reference order",
        "parameters": {"input_images": [
            {"source": "library", "image_id": library_image["id"], "name": "Library first"},
            {"source": "uploaded", "name": "Upload second", "data_url": upload_data_url},
        ]},
    }).json()
    cloned_reference = job["parameters"]["input_images"][0]["result_path"]
    assert cloned_reference.startswith(f"generation-references/{job['id']}/")
    assert (tmp_path / "library" / cloned_reference).is_file()
    assert c.delete(f"/api/items/{source_item['id']}").status_code == 200

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 200
    assert [image["source"] for image in captured["input_images"]] == ["library", "uploaded"]
    assert [image["name"] for image in captured["input_images"]] == ["Library first", "Upload second"]


def test_codex_native_rejects_invalid_data_url_before_provider_call(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    called = False

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        nonlocal called
        called = True
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "image_edit",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "Make this more painterly",
        "parameters": {"input_images": [{"source": "uploaded", "name": "bad.png", "data_url": "data:image/png;base64,not-base64"}]},
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 409
    assert called is False
    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert "input image" in failed["error"].lower()


def test_codex_native_marks_failed_when_stage_result_rejects_unsafe_result_root(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
    }).json()
    wrong_results = tmp_path / "library" / "wrong-results"
    wrong_results.mkdir()
    try:
        (tmp_path / "library" / "generation-results").symlink_to(wrong_results, target_is_directory=True)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 409
    assert list(wrong_results.rglob("*")) == []
    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["started_at"] is not None
    assert failed["completed_at"] is not None
    assert "path" in failed["error"].lower()


def test_codex_native_rejects_legacy_unsafe_result_path_before_provider_call(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    called = False

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        nonlocal called
        called = True
        return base64.b64encode(png_bytes()).decode()

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "image_edit",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "Make this more painterly",
    }).json()
    outside_image = tmp_path / "secret.png"
    outside_image.write_bytes(png_bytes("red"))
    legacy_parameters = {"input_images": [{"result_path": "../secret.png", "name": "secret.png"}]}
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), job["id"]))
        conn.commit()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")

    assert response.status_code == 409
    assert called is False
    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert "input image" in failed["error"].lower()


def test_codex_native_surfaces_non_200_responses_without_secrets():
    import httpx
    from backend.services.openai_codex_native import _codex_response_error_message

    response = httpx.Response(400, json={"error": {"message": "Tool 'image_generation' is not supported with gpt-5.3-codex-spark. access_token=secret"}})

    assert _codex_response_error_message(response) == "Codex Responses API returned status 400: Generation failed; provider returned a credential-related error"


@pytest.mark.parametrize("marker", ("AUTHORIZATION: secret", "Bearer secret", "ID_TOKEN=secret"))
def test_codex_native_response_error_redacts_credential_markers_case_insensitively(marker):
    import httpx
    from backend.services.openai_codex_native import _codex_response_error_message

    response = httpx.Response(503, json={"error": {"message": f"Provider unavailable. {marker}"}})

    message = _codex_response_error_message(response)
    assert message == "Codex Responses API returned status 503: Generation failed; provider returned a credential-related error"
    assert "secret" not in message


def test_codex_native_response_error_uses_safe_error_code_for_classification():
    import httpx
    from backend.services.generation_jobs import _classify_error
    from backend.services.openai_codex_native import _codex_response_error_message

    response = httpx.Response(400, json={"error": {"code": "invalid_api_key", "message": "invalid credentials"}})

    message = _codex_response_error_message(response)
    assert _classify_error(message) == "auth_required"
    assert "api_key" not in message


def test_codex_native_run_marks_job_failed_on_provider_errors(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})

    def fail_collect(self, prompt, *, size, quality, image_model, orchestrator_model, input_images=None):
        raise openai_codex_native.CodexNativeAuthError("upstream failed with access_token=[REDACTED]")

    monkeypatch.setattr(openai_codex_native.OpenAICodexNativeProvider, "_collect_image_b64", fail_collect)

    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 409
    assert response.json()["detail"] == "Generation failed; provider returned a credential-related error"
    assert "access_token" not in response.text
    assert "[REDACTED]" not in response.text

    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["started_at"] is not None
    assert failed["completed_at"] is not None
    assert failed["error"] == "Generation failed; provider returned a credential-related error"
    assert "access_token" not in json.dumps(failed)


def test_generation_job_api_sanitizes_legacy_provider_errors_on_read(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "A legacy failed job",
    }).json()

    legacy_error = "UPSTREAM ACCESS_TOKEN=legacy-secret"
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET status='failed', error=?, completed_at=updated_at WHERE id=?",
            (legacy_error, job["id"]),
        )
        conn.commit()

    detail = c.get(f"/api/generation-jobs/{job['id']}")
    listed = c.get("/api/generation-jobs")

    assert detail.status_code == 200
    assert listed.status_code == 200
    assert detail.json()["error"] == "Generation failed; provider returned a credential-related error"
    assert "legacy-secret" not in detail.text
    assert "legacy-secret" not in listed.text


def test_retry_after_parser_accepts_seconds_and_http_date_and_clamps():
    from backend.services.openai_codex_native import parse_retry_after_seconds

    reference = datetime(2026, 7, 19, 7, 0, tzinfo=timezone.utc)
    http_date = (reference + timedelta(seconds=12)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after_seconds("0") == 0
    assert parse_retry_after_seconds("12") == 12
    assert parse_retry_after_seconds("999") == 300
    assert parse_retry_after_seconds(http_date, now=reference) == 12
    assert parse_retry_after_seconds("not-a-duration") is None


def test_codex_native_http_429_retry_after_zero_is_recorded_once(tmp_path, monkeypatch):
    import httpx
    from backend.services import openai_codex_native
    from backend.services.generation_jobs import GenerationJobRepository
    from backend.services.openai_codex_native import CodexNativeAuthStore

    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)
    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})

    def rate_limited(_request):
        return httpx.Response(
            429,
            headers={"Retry-After": "0"},
            json={"error": {"code": "rate_limit_exceeded", "message": "Too many requests"}},
        )

    transport = httpx.MockTransport(rate_limited)
    real_client = httpx.Client

    def mock_client(*args, **kwargs):
        return real_client(*args, **{**kwargs, "transport": transport})

    monkeypatch.setattr(openai_codex_native.httpx, "Client", mock_client)
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_text": "A neon library in the rain",
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 409
    assert "Too many requests" in response.json()["detail"]
    assert "refresh-secret" not in response.text

    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["metadata"]["error_kind"] == "rate_limited"
    assert failed["metadata"]["retry_after_seconds"] == 0
    state = GenerationJobRepository(tmp_path / "library").get_provider_queue_state("openai_codex_oauth_native")
    assert state.paused is False
    assert state.retry_after_seconds == 0
    assert state.backoff_seconds == 0
    with connect(tmp_path / "library") as conn:
        assert conn.execute(
            "SELECT incident_count FROM provider_queue_states WHERE provider=?",
            ("openai_codex_oauth_native",),
        ).fetchone()[0] == 1


def test_codex_image_tool_requests_only_final_image(tmp_path, monkeypatch):
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore, OpenAICodexNativeProvider

    auth_store = CodexNativeAuthStore(tmp_path / "auth.json")
    auth_store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh"})
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps({
                "type": "response.output_item.done",
                "item": {"type": "image_generation_call", "result": base64.b64encode(b"image").decode()},
            })
            yield "data: [DONE]"

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def stream(self, method, url, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(openai_codex_native.httpx, "Client", lambda *args, **kwargs: FakeClient())
    result = OpenAICodexNativeProvider(auth_store=auth_store)._collect_image_b64(
        "A test image",
        size=None,
        quality="high",
        image_model="gpt-image-2",
        orchestrator_model="gpt-5.6-luna",
    )
    assert result == base64.b64encode(b"image").decode()
    assert captured["json"]["tools"][0]["partial_images"] == 0


def test_codex_image_tool_never_promotes_partial_event_to_final_result(tmp_path, monkeypatch):
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import (
        CodexNativeAuthError,
        CodexNativeAuthStore,
        OpenAICodexNativeProvider,
    )

    auth_store = CodexNativeAuthStore(tmp_path / "auth.json")
    auth_store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh"})

    class FakeResponse:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps({
                "type": "response.image_generation_call.partial_image",
                "partial_image_b64": base64.b64encode(b"preview-only").decode(),
            })
            yield "data: [DONE]"

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def stream(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(openai_codex_native.httpx, "Client", lambda *args, **kwargs: FakeClient())
    with pytest.raises(CodexNativeAuthError, match="no image_generation result"):
        OpenAICodexNativeProvider(auth_store=auth_store)._collect_image_b64(
            "A test image",
            size=None,
            quality="high",
            image_model="gpt-image-2",
            orchestrator_model="gpt-5.6-luna",
        )


def test_title_suggestion_normalizes_provider_output():
    from backend.services.openai_codex_native import normalize_title_suggestion

    assert normalize_title_suggestion('Suggested title: “Neon Library in Rain”\n') == "Neon Library in Rain"
    assert normalize_title_suggestion("標題：冰藍星河禮服") == "冰藍星河禮服"


def test_title_suggestion_request_contains_prompt_text_only(tmp_path, monkeypatch):
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore, OpenAICodexNativeProvider

    auth_store = CodexNativeAuthStore(tmp_path / "auth.json")
    auth_store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh"})
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps({"type": "response.output_text.delta", "delta": "Neon Library"})
            yield "data: [DONE]"

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def stream(self, method, url, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(openai_codex_native.httpx, "Client", lambda *args, **kwargs: FakeClient())
    title = OpenAICodexNativeProvider(auth_store=auth_store)._collect_title_text("A neon library in the rain")

    assert title == "Neon Library"
    assert captured["json"]["model"] == "gpt-5.6-terra"
    assert captured["json"]["input"] == [{
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "A neon library in the rain"}],
    }]
    assert "max_output_tokens" not in captured["json"]
    assert "tools" not in captured["json"]


def test_title_suggestion_does_not_report_upstream_bad_request_as_login_required(tmp_path, monkeypatch):
    import httpx

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import (
        CodexNativeAuthStore,
        CodexNativeRequestError,
        OpenAICodexNativeProvider,
    )

    auth_store = CodexNativeAuthStore(tmp_path / "auth.json")
    auth_store.save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh"})
    http_client = httpx.Client
    transport = httpx.MockTransport(lambda _request: httpx.Response(400))
    monkeypatch.setattr(openai_codex_native.httpx, "Client", lambda *args, **kwargs: http_client(transport=transport))

    with pytest.raises(CodexNativeRequestError):
        OpenAICodexNativeProvider(auth_store=auth_store)._collect_title_text("A neon library in the rain")


def test_title_suggestion_api_passes_only_library_and_prompt(tmp_path, monkeypatch):
    from backend.services.openai_codex_native import OpenAICodexNativeProvider

    captured = {}

    def suggest_title(self, library_path, prompt_text):
        captured.update(library_path=Path(library_path), prompt_text=prompt_text)
        return "Neon Library in Rain"

    monkeypatch.setattr(OpenAICodexNativeProvider, "suggest_title", suggest_title)
    response = client(tmp_path).post(
        "/api/generation-providers/openai-codex-native/suggest-title",
        json={"prompt_text": "A neon library in the rain"},
    )

    assert response.status_code == 200
    assert response.json() == {"title": "Neon Library in Rain"}
    assert captured == {
        "library_path": tmp_path / "library",
        "prompt_text": "A neon library in the rain",
    }


@pytest.mark.parametrize(("error_type", "status_code", "retry_after"), [
    ("auth", 409, None),
    ("request", 502, None),
    ("temporary", 503, None),
    ("rate_limit", 429, "75"),
])
def test_title_suggestion_api_returns_sanitized_errors(tmp_path, monkeypatch, error_type, status_code, retry_after):
    from backend.services.openai_codex_native import (
        CodexNativeAuthError,
        CodexNativeRateLimitError,
        CodexNativeRequestError,
        CodexNativeTemporaryError,
        OpenAICodexNativeProvider,
    )

    errors = {
        "auth": CodexNativeAuthError("refresh-secret"),
        "request": CodexNativeRequestError("provider raw response refresh-secret"),
        "temporary": CodexNativeTemporaryError("provider raw response refresh-secret"),
        "rate_limit": CodexNativeRateLimitError("provider raw response refresh-secret", retry_after_seconds=75),
    }

    def suggest_title(self, library_path, prompt_text):
        raise errors[error_type]

    monkeypatch.setattr(OpenAICodexNativeProvider, "suggest_title", suggest_title)
    response = client(tmp_path).post(
        "/api/generation-providers/openai-codex-native/suggest-title",
        json={"prompt_text": "A neon library in the rain"},
    )

    assert response.status_code == status_code
    assert "refresh-secret" not in response.text
    assert response.headers.get("Retry-After") == retry_after
