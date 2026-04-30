import base64
import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

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


def test_codex_native_uses_gpt_55_as_default_orchestration_model():
    from backend.services.openai_codex_native import CODEX_CHAT_MODEL, DEFAULT_CODEX_ORCHESTRATOR_MODELS, codex_orchestrator_models

    assert CODEX_CHAT_MODEL == "gpt-5.5"
    assert DEFAULT_CODEX_ORCHESTRATOR_MODELS == ["gpt-5.5", "gpt-5.3-codex-spark"]
    assert codex_orchestrator_models()[:2] == ["gpt-5.5", "gpt-5.3-codex-spark"]


def test_codex_native_status_exposes_orchestrator_and_image_models(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_ORCHESTRATOR_MODELS", "gpt-5.5,gpt-5.3-codex-spark")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})
    c = client(tmp_path)

    codex = next(provider for provider in c.get("/api/generation-providers").json() if provider["provider"] == "openai_codex_oauth_native")

    assert codex["orchestrator_models"] == ["gpt-5.5", "gpt-5.3-codex-spark"]
    assert codex["default_orchestrator_model"] == "gpt-5.5"
    assert codex["image_models"] == ["gpt-image-2"]
    assert codex["default_image_model"] == "gpt-image-2"


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
        lambda self, prompt, *, size, quality, image_model, orchestrator_model: base64.b64encode(png_bytes()).decode(),
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

    def collect(self, prompt, *, size, quality, image_model, orchestrator_model):
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
        "orchestrator_model": "gpt-5.5",
    }
    assert payload["metadata"]["requested_aspect_ratio"] == "4:3"
    assert payload["metadata"]["aspect_ratio_prompt_injection"] == "Make the aspect ratio 4:3."
    assert payload["metadata"]["effective_prompt"] == captured["prompt"]
    assert payload["metadata"]["size"] == "auto"
    assert payload["metadata"]["native_size_parameter"] is None


def test_codex_native_run_marks_job_failed_on_provider_errors(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda *args, **kwargs: None)

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})

    def fail_collect(self, prompt, *, size, quality, image_model, orchestrator_model):
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
