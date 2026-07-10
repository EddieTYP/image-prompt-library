import base64
import json
import os
import subprocess
import sys
import threading
import time
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


@pytest.mark.parametrize("failure", ["network", "server"])
def test_codex_native_refresh_maps_transient_failures_to_temporary_error(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services.openai_codex_native import CodexNativeAuthStore, CodexNativeTemporaryError

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(503)

    store = CodexNativeAuthStore(tmp_path / "auth" / "auth.json")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(CodexNativeTemporaryError):
            store.refresh_tokens("refresh-secret", http_client=http_client)


def test_codex_native_malformed_local_credentials_raise_auth_error(tmp_path):
    from backend.services.openai_codex_native import CodexNativeAuthError, CodexNativeAuthStore

    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{", encoding="utf-8")

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


def test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    import httpx
    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    store = CodexNativeAuthStore(auth_path)
    store.save_tokens({"access_token": fake_jwt(exp=1), "refresh_token": "refresh-token-old"})
    lock_path = auth_path.with_name(f"{auth_path.name}.refresh.lock")
    lock_path.mkdir()
    assert getattr(openai_codex_native, "AUTH_REFRESH_LOCK_POLL_SECONDS", None) == 0.1
    assert getattr(openai_codex_native, "AUTH_REFRESH_LOCK_WAIT_SECONDS", None) == 20.0
    stale_seconds = getattr(openai_codex_native, "AUTH_REFRESH_LOCK_STALE_SECONDS", None)
    assert stale_seconds == 30.0
    stale_time = time.time() - stale_seconds - 1
    os.utime(lock_path, (stale_time, stale_time))
    refreshed = store.read_tokens(http_client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "access_token": fake_jwt("acct_refreshed"),
            "refresh_token": "refresh-token-rotated",
        })
    )))

    assert refreshed["access_token"] == fake_jwt("acct_refreshed")
    assert lock_path.exists() is False

    store.save_tokens({"access_token": fake_jwt(exp=1), "refresh_token": "refresh-token-old"})
    lock_path.mkdir()
    monkeypatch.setattr(openai_codex_native, "AUTH_REFRESH_LOCK_WAIT_SECONDS", 0)
    temporary_error = getattr(openai_codex_native, "CodexNativeTemporaryError", RuntimeError)

    with pytest.raises(temporary_error):
        store.read_tokens()

    assert lock_path.exists()


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

    assert CODEX_CHAT_MODEL == "gpt-5.4"
    assert DEFAULT_CODEX_ORCHESTRATOR_MODELS == ["gpt-5.4", "gpt-5.5", "gpt-5.3-codex"]
    assert codex_orchestrator_models() == ["gpt-5.4", "gpt-5.5", "gpt-5.3-codex"]


def test_codex_native_filters_known_text_only_orchestrator_models_from_env(monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_ORCHESTRATOR_MODELS", "gpt-5.5,gpt-5.3-codex-spark,gpt-5.3,gpt-5.4")

    from backend.services.openai_codex_native import codex_orchestrator_models

    assert codex_orchestrator_models() == ["gpt-5.4", "gpt-5.5", "gpt-5.3-codex"]


def test_codex_native_status_exposes_orchestrator_and_image_models(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_ORCHESTRATOR_MODELS", "gpt-5.5,gpt-5.3-codex-spark")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    c = client(tmp_path)

    codex = next(provider for provider in c.get("/api/generation-providers").json() if provider["provider"] == "openai_codex_oauth_native")

    assert codex["orchestrator_models"] == ["gpt-5.4", "gpt-5.5", "gpt-5.3-codex"]
    assert codex["default_orchestrator_model"] == "gpt-5.4"
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
        "orchestrator_model": "gpt-5.4",
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

    assert _codex_response_error_message(response) == "Codex Responses API returned status 400: Tool 'image_generation' is not supported with gpt-5.3-codex-spark."


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

    failed = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["started_at"] is not None
    assert failed["completed_at"] is not None
    assert failed["error"] == "Generation failed; provider returned a credential-related error"
    assert "access_token" not in json.dumps(failed)
