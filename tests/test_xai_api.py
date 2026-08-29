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
from backend.services.xai_api import MODEL, XAIAPIAuthError, XAIAPIError, XAIAPIProvider, XAIAPIRateLimitError


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
