import base64
import json
import os
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app


def png_bytes(color="purple", size=(16, 10)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def fake_jwt(account_id="acct_test_123") -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
        "exp": 4_102_444_800,
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
    assert status == {
        "provider": "openai_codex_oauth_native",
        "auth_mode": "codex_oauth_native",
        "available": True,
        "token_present": True,
        "account_id": "acct_test_123",
        "auth_store_path": str(auth_path),
    }
    assert "refresh-secret" not in json.dumps(status)
    assert "access_token" not in status
    assert codex_cloudflare_headers(fake_jwt())["ChatGPT-Account-ID"] == "acct_test_123"


def test_codex_native_status_api_does_not_expose_tokens_or_use_library_path(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth-outside-library" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    c = client(tmp_path)

    response = c.get("/api/generation-providers/openai-codex-native/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai_codex_oauth_native"
    assert payload["available"] is False
    assert payload["token_present"] is False
    assert payload["auth_store_path"] == str(auth_path)
    assert str(tmp_path / "library") not in payload["auth_store_path"]
    assert "token" not in json.dumps(payload).lower().replace("token_present", "")


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


def test_codex_native_run_executes_job_and_stages_result_without_leaking_tokens(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})
    monkeypatch.setattr(
        openai_codex_native.OpenAICodexNativeProvider,
        "_collect_image_b64",
        lambda self, prompt, *, size, quality: base64.b64encode(png_bytes()).decode(),
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


def test_codex_native_run_marks_job_failed_on_provider_errors(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))

    from backend.services import openai_codex_native
    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "***"})

    def fail_collect(self, prompt, *, size, quality):
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
