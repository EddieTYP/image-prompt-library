import base64
import json
from io import BytesIO

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest

from backend.main import create_app
from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobRepository
from backend.services.xai_api import (
    MODEL,
    XAIAPIAuthError,
    XAIAPIError,
    XAIAPIKeyStore,
    XAIAPIProvider,
    XAIAPIRateLimitError,
    xai_api_key,
    xai_status,
)


def png_bytes(color="purple", size=(16, 10)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def image_response(*, zero_data_retention="false") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-zero-data-retention": zero_data_retention},
        json={
            "data": [{
                "b64_json": base64.b64encode(png_bytes()).decode("ascii"),
                "mime_type": "image/png",
            }],
        },
    )


def test_xai_status_is_optional_and_never_exposes_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-secret-canary")
    client = TestClient(create_app(library_path=tmp_path / "library"))

    providers = client.get("/api/generation-providers").json()
    xai = next(provider for provider in providers if provider["provider"] == "xai_api")

    assert xai["display_name"] == "xAI Grok Imagine"
    assert xai["auth_mode"] == "api_key_env"
    assert xai["available"] is True
    assert xai["default_image_model"] == MODEL
    assert xai["quality_options"] == ["low", "medium"]
    assert xai["max_input_images"] == 3
    assert xai["retention_days"] == 30
    assert "xai-secret-canary" not in json.dumps(providers)


def test_xai_local_key_store_is_redacted_and_environment_takes_precedence(tmp_path, monkeypatch):
    auth_path = tmp_path / "app-state" / "codex-auth.json"
    store = XAIAPIKeyStore(auth_path.with_name("xai-api-key.json"))
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    store.save_key("xai-local-secret-canary")

    status = xai_status(store)
    assert xai_api_key(store) == "xai-local-secret-canary"
    assert status["auth_mode"] == "api_key_local"
    assert status["credential_source"] == "local_store"
    assert status["managed_by_environment"] is False
    assert status["key_present"] is True
    assert "xai-local-secret-canary" not in json.dumps(status)
    assert str(store.path) not in json.dumps(status)

    monkeypatch.setenv("XAI_API_KEY", "xai-environment-secret-canary")
    environment_status = xai_status(store)
    assert xai_api_key(store) == "xai-environment-secret-canary"
    assert environment_status["auth_mode"] == "api_key_env"
    assert environment_status["credential_source"] == "environment"
    assert environment_status["managed_by_environment"] is True
    assert "secret-canary" not in json.dumps(environment_status)


def test_xai_api_key_can_be_saved_and_removed_without_exposing_it(tmp_path, monkeypatch):
    library = tmp_path / "library"
    auth_path = tmp_path / "app-state" / "codex-auth.json"
    key_path = auth_path.with_name("xai-api-key.json")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    client = TestClient(create_app(library_path=library))

    saved = client.post(
        "/api/generation-providers/xai-api/api-key",
        json={"api_key": "xai-saved-secret-canary"},
    )

    assert saved.status_code == 200
    assert key_path.is_file()
    assert saved.json()["credential_source"] == "local_store"
    assert saved.json()["managed_by_environment"] is False
    assert "xai-saved-secret-canary" not in saved.text
    providers = client.get("/api/generation-providers").text
    assert "xai-saved-secret-canary" not in providers

    removed = client.delete("/api/generation-providers/xai-api/api-key")

    assert removed.status_code == 200
    assert removed.json()["configured"] is False
    assert not key_path.exists()


def test_xai_provider_uses_saved_local_key_and_records_local_auth_mode(tmp_path, monkeypatch):
    library = tmp_path / "library"
    auth_path = tmp_path / "app-state" / "codex-auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    XAIAPIKeyStore().save_key("xai-local-generation-canary")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return image_response()

    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(
        provider="xai_api",
        model=MODEL,
        prompt_text="A saved-key generation test",
    ))
    provider = XAIAPIProvider(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = provider.run_job(library, job.id)

    assert result.status == "succeeded"
    assert requests[0].headers["Authorization"] == "Bearer xai-local-generation-canary"
    assert result.metadata["auth_mode"] == "api_key_local"
    assert "xai-local-generation-canary" not in json.dumps(result.model_dump())


def test_xai_api_key_ui_cannot_replace_environment_managed_key(tmp_path, monkeypatch):
    auth_path = tmp_path / "app-state" / "codex-auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("XAI_API_KEY", "xai-environment-secret-canary")
    client = TestClient(create_app(library_path=tmp_path / "library"))

    saved = client.post(
        "/api/generation-providers/xai-api/api-key",
        json={"api_key": "xai-replacement-secret-canary"},
    )
    removed = client.delete("/api/generation-providers/xai-api/api-key")

    assert saved.status_code == 409
    assert removed.status_code == 409
    assert "secret-canary" not in saved.text
    assert "secret-canary" not in removed.text


def test_xai_text_generation_uses_base64_response_and_stores_safe_provenance(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return image_response(zero_data_retention="true")

    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(
        provider="xai_api",
        model=MODEL,
        prompt_text="A quiet library at night",
        parameters={"quality": "low", "requested_aspect_ratio": "16:9"},
    ))
    provider = XAIAPIProvider(
        api_key="xai-secret-canary",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.run_job(library, job.id)

    assert result.status == "succeeded"
    assert requests[0].url.path == "/v1/images/generations"
    assert requests[0].headers["Authorization"] == "Bearer xai-secret-canary"
    payload = json.loads(requests[0].content)
    assert payload == {
        "model": MODEL,
        "prompt": "A quiet library at night",
        "quality": "low",
        "resolution": "1k",
        "aspect_ratio": "16:9",
        "response_format": "b64_json",
    }
    assert result.metadata["provider"] == "xai_api"
    assert result.metadata["model"] == MODEL
    assert result.metadata["zero_data_retention"] is True
    assert "xai-secret-canary" not in json.dumps(result.model_dump())


def test_xai_multi_image_edit_sends_ordered_images_and_caps_inputs(tmp_path):
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return image_response()

    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    data_urls = [
        f"data:image/png;base64,{base64.b64encode(png_bytes(color)).decode('ascii')}"
        for color in ("red", "blue")
    ]
    job = repo.create_job(GenerationJobCreate(
        provider="xai_api",
        model=MODEL,
        mode="image_edit",
        prompt_text="Combine both references",
        parameters={
            "quality": "high",
            "requested_aspect_ratio": "3:4",
            "input_images": [
                {"source": "uploaded", "data_url": data_url}
                for data_url in data_urls
            ],
        },
    ))
    provider = XAIAPIProvider(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.run_job(library, job.id)

    assert result.status == "succeeded"
    assert result.metadata["input_image_count"] == 2
    assert result.metadata["quality"] == "medium"
    assert payloads[0]["quality"] == "medium"
    assert payloads[0]["aspect_ratio"] == "3:4"
    assert [image["url"] for image in payloads[0]["images"]] == data_urls

    too_many = repo.create_job(GenerationJobCreate(
        provider="xai_api",
        model=MODEL,
        mode="image_edit",
        prompt_text="Too many references",
        parameters={
            "input_images": [
                {"source": "uploaded", "data_url": data_urls[index % 2]}
                for index in range(4)
            ],
        },
    ))
    with pytest.raises(XAIAPIError, match="up to 3 input images"):
        provider.run_job(library, too_many.id)
    assert repo.get_job(too_many.id).status == "failed"


def test_xai_rate_limit_and_missing_key_fail_safely(tmp_path):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    limited = repo.create_job(GenerationJobCreate(provider="xai_api", model=MODEL, prompt_text="Rate limited"))
    provider = XAIAPIProvider(
        api_key="xai-secret-canary",
        http_client=httpx.Client(transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, headers={"Retry-After": "9"}),
        )),
    )

    with pytest.raises(XAIAPIRateLimitError) as exc_info:
        provider.run_job(library, limited.id)

    assert exc_info.value.retry_after_seconds == 9
    assert repo.get_job(limited.id).status == "failed"
    assert repo.get_provider_queue_state("xai_api").paused_until is not None
    assert "xai-secret-canary" not in json.dumps(repo.get_job(limited.id).model_dump())

    missing = repo.create_job(GenerationJobCreate(provider="xai_api", model=MODEL, prompt_text="Missing key"))
    with pytest.raises(XAIAPIAuthError, match="credential-related error"):
        XAIAPIProvider(api_key="").run_job(library, missing.id)
    failed = repo.get_job(missing.id)
    assert failed.status == "failed"
    assert failed.started_at is not None
    assert failed.metadata["error_kind"] == "auth_required"
