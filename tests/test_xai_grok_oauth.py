import base64
import json
from io import BytesIO

import httpx
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.main import create_app
from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobRepository


def png_bytes(color="teal", size=(12, 8)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def isolated_provider_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(tmp_path / "app-state" / "codex-auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_GROK_AUTH_PATH", str(tmp_path / "app-state" / "grok-auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))
    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_GROK_CLIENT_ID", raising=False)


def test_grok_status_is_optional_separate_and_redacted(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore

    store = GrokOAuthAuthStore()
    assert store.status()["state"] == "not_connected"
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})

    status = store.status()
    serialized = json.dumps(status)
    assert status["provider"] == "xai_grok_oauth"
    assert status["display_name"] == "Grok OAuth · Experimental"
    assert status["authenticated"] is True
    assert status["features"] == {
        "text_to_image": True,
        "text_reference_to_image": True,
        "image_edit": True,
        "title_suggestion": True,
    }
    assert status["max_input_images"] == 3
    assert "access-secret" not in serialized
    assert "refresh-secret" not in serialized
    assert store.path.name == "grok-auth.json"


def test_grok_title_suggestion_uses_responses_api_and_normalizes(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore, XaiGrokOAuthProvider

    library = tmp_path / "library"
    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.x.ai/v1/responses"
        assert request.headers["authorization"] == "Bearer access-secret"
        assert json.loads(request.content) == {
            "model": "grok-4.6",
            "store": False,
            "reasoning": {"effort": "low"},
            "max_output_tokens": 128,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Suggest one concise library title for the image prompt. "
                        "Use the same language as the prompt. Return only the title, without quotes, labels, markdown, or commentary."
                    ),
                },
                {"role": "user", "content": "雨夜中的霓虹圖書館"},
            ],
        }
        return httpx.Response(200, json={
            "output": [{"content": [{"type": "output_text", "text": "標題：霓虹雨夜圖書館"}]}],
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        title = XaiGrokOAuthProvider(auth_store=store, http_client=http_client).suggest_title(
            library,
            "雨夜中的霓虹圖書館",
        )

    assert title == "霓虹雨夜圖書館"


def test_grok_title_suggestion_rejects_unsafe_credential_boundary_before_auth_read(tmp_path, monkeypatch):
    from backend.services.xai_grok_oauth import GrokOAuthError, XaiGrokOAuthProvider

    library = tmp_path / "library"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_GROK_AUTH_PATH", str(library / "grok-auth.json"))

    with pytest.raises(GrokOAuthError, match="paths are unsafe"):
        XaiGrokOAuthProvider().suggest_title(library, "A quiet observatory")


def test_grok_title_suggestion_treats_upstream_entitlement_failure_as_sanitized_request_error(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore, GrokOAuthRequestError, XaiGrokOAuthProvider

    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(403, text="private upstream detail"))) as http_client:
        with pytest.raises(GrokOAuthRequestError, match="access is unavailable"):
            XaiGrokOAuthProvider(auth_store=store, http_client=http_client).suggest_title(
                tmp_path / "library",
                "A quiet observatory",
            )


def test_grok_title_suggestion_rejects_malformed_success_response(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore, GrokOAuthRequestError, XaiGrokOAuthProvider

    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"output": None}))) as http_client:
        with pytest.raises(GrokOAuthRequestError, match="invalid response"):
            XaiGrokOAuthProvider(auth_store=store, http_client=http_client).suggest_title(
                tmp_path / "library",
                "A quiet observatory",
            )


def test_grok_title_suggestion_api_routes_provider_and_returns_provenance(tmp_path, monkeypatch):
    from backend.services.xai_grok_oauth import XaiGrokOAuthProvider

    captured = {}

    def suggest_title(self, library_path, prompt_text):
        captured.update(library_path=library_path, prompt_text=prompt_text)
        return "Quiet Observatory"

    monkeypatch.setattr(XaiGrokOAuthProvider, "suggest_title", suggest_title)
    response = TestClient(create_app(library_path=tmp_path / "library")).post(
        "/api/generation-providers/xai_grok_oauth/suggest-title",
        json={"prompt_text": "A quiet observatory"},
    )

    assert response.status_code == 200
    assert response.json() == {"title": "Quiet Observatory", "provider": "xai_grok_oauth"}
    assert captured == {"library_path": tmp_path / "library", "prompt_text": "A quiet observatory"}


@pytest.mark.parametrize(("error_type", "status_code", "retry_after"), [
    ("auth", 409, None),
    ("request", 502, None),
    ("temporary", 503, None),
    ("rate_limit", 429, "45"),
])
def test_grok_title_suggestion_api_returns_sanitized_errors(tmp_path, monkeypatch, error_type, status_code, retry_after):
    from backend.services.xai_grok_oauth import (
        GrokOAuthError,
        GrokOAuthRateLimitError,
        GrokOAuthRequestError,
        GrokOAuthTemporaryError,
        XaiGrokOAuthProvider,
    )

    errors = {
        "auth": GrokOAuthError("access-secret"),
        "request": GrokOAuthRequestError("provider raw response access-secret"),
        "temporary": GrokOAuthTemporaryError("provider raw response access-secret"),
        "rate_limit": GrokOAuthRateLimitError("provider raw response access-secret", retry_after_seconds=45),
    }

    def suggest_title(self, library_path, prompt_text):
        raise errors[error_type]

    monkeypatch.setattr(XaiGrokOAuthProvider, "suggest_title", suggest_title)
    response = TestClient(create_app(library_path=tmp_path / "library")).post(
        "/api/generation-providers/xai_grok_oauth/suggest-title",
        json={"prompt_text": "A quiet observatory"},
    )

    assert response.status_code == status_code
    assert "access-secret" not in response.text
    assert response.headers.get("Retry-After") == retry_after


def test_title_suggestion_unknown_provider_returns_not_found(tmp_path):
    response = TestClient(create_app(library_path=tmp_path / "library")).post(
        "/api/generation-providers/unknown_provider/suggest-title",
        json={"prompt_text": "A quiet observatory"},
    )

    assert response.status_code == 404


def test_grok_client_id_can_be_overridden_by_local_config(tmp_path):
    from backend.services.xai_grok_oauth import configured_client_id

    config_path = tmp_path / "app-state" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({
        "providers": {"xai_grok_oauth": {"client_id": "local-grok-client"}},
    }), encoding="utf-8")

    assert configured_client_id() == "local-grok-client"


def test_grok_device_flow_uses_standard_device_grant_and_saves_approved_tokens(tmp_path):
    from backend.services.xai_grok_oauth import GrokDeviceCodeFlow, GrokOAuthAuthStore

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth2/device/code":
            return httpx.Response(200, json={
                "device_code": "device-secret",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://auth.x.ai/device",
                "verification_uri_complete": "https://auth.x.ai/device?user_code=ABCD-EFGH",
                "expires_in": 900,
                "interval": 5,
            })
        return httpx.Response(200, json={
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_in": 3600,
        })

    store = GrokOAuthAuthStore()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        flow = GrokDeviceCodeFlow(auth_store=store, http_client=http_client)
        started = flow.start()
        approved = flow.poll_device_authorization(started["device_code"])

    assert started["verification_url"].endswith("user_code=ABCD-EFGH")
    assert approved["authenticated"] is True
    start_form = requests[0].content.decode()
    poll_form = requests[1].content.decode()
    assert "scope=openid" in start_form
    assert "referrer=image-prompt-library" in start_form
    assert "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code" in poll_form
    assert "device_code=device-secret" in poll_form


def test_grok_device_flow_reports_pending_without_writing_tokens(tmp_path):
    from backend.services.xai_grok_oauth import GrokDeviceCodeFlow, GrokOAuthAuthStore

    store = GrokOAuthAuthStore()
    transport = httpx.MockTransport(lambda _request: httpx.Response(400, json={"error": "authorization_pending"}))
    with httpx.Client(transport=transport) as http_client:
        result = GrokDeviceCodeFlow(auth_store=store, http_client=http_client).poll_device_authorization("device-secret")

    assert result["status"] == "pending"
    assert store.path.exists() is False


def test_grok_refresh_preserves_refresh_token_when_not_rotated(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore

    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "expired-access", "refresh_token": "original-refresh", "expires_in": 0})
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={
        "access_token": "fresh-access",
        "expires_in": 3600,
    }))
    with httpx.Client(transport=transport) as http_client:
        tokens = store.read_tokens(http_client=http_client)

    assert tokens["access_token"] == "fresh-access"
    assert tokens["refresh_token"] == "original-refresh"


def test_grok_provider_generates_and_records_provider_model_provenance(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore, XaiGrokOAuthProvider

    library = tmp_path / "library"
    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})
    image_data = png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.x.ai/v1/images/generations"
        assert request.headers["authorization"] == "Bearer access-secret"
        payload = json.loads(request.content)
        assert payload == {
            "model": "grok-imagine-image-2.0",
            "prompt": "A quiet observatory",
            "n": 1,
            "aspect_ratio": "16:9",
            "quality": "low",
            "resolution": "2k",
            "response_format": "b64_json",
        }
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image_data).decode()}]})

    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(
        provider="xai_grok_oauth",
        model="grok-imagine-image-2.0",
        prompt_text="A quiet observatory",
        parameters={"requested_aspect_ratio": "16:9", "quality": "low", "resolution": "2k"},
    ))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = XaiGrokOAuthProvider(auth_store=store, http_client=http_client).run_job(library, job.id)

    assert result.status == "succeeded"
    assert result.result_width == 12
    assert result.result_height == 8
    assert result.metadata["provider"] == "xai_grok_oauth"
    assert result.metadata["model"] == "grok-imagine-image-2.0"
    assert result.metadata["auth_mode"] == "grok_oauth_device"
    assert result.metadata["quality"] == "low"
    assert result.metadata["resolution"] == "2k"
    assert result.metadata["mode"] == "text_to_image"
    assert result.metadata["input_image_count"] == 0
    assert "access-secret" not in json.dumps(result.metadata)


def test_grok_provider_edits_one_data_url_image_with_quality_and_resolution(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore, XaiGrokOAuthProvider

    library = tmp_path / "library"
    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})
    source_data = png_bytes(color="navy")
    result_data = png_bytes(color="gold")
    source_url = f"data:image/png;base64,{base64.b64encode(source_data).decode()}"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.x.ai/v1/images/edits"
        payload = json.loads(request.content)
        assert payload == {
            "model": "grok-imagine-image-2.0",
            "prompt": "Add a gold border",
            "aspect_ratio": "4:3",
            "quality": "medium",
            "resolution": "2k",
            "response_format": "b64_json",
            "image": {"type": "image_url", "url": source_url},
        }
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(result_data).decode()}]})

    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(
        provider="xai_grok_oauth",
        model="grok-imagine-image-2.0",
        prompt_text="Add a gold border",
        parameters={
            "requested_aspect_ratio": "4:3",
            "quality": "medium",
            "resolution": "2k",
            "input_images": [{"source": "uploaded", "name": "source.png", "data_url": source_url}],
        },
    ))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = XaiGrokOAuthProvider(auth_store=store, http_client=http_client).run_job(library, job.id)

    assert result.status == "succeeded"
    assert result.metadata["mode"] == "image_edit"
    assert result.metadata["input_image_count"] == 1


def test_grok_provider_preserves_multi_image_edit_order(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore, XaiGrokOAuthProvider

    library = tmp_path / "library"
    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})
    source_urls = [
        f"data:image/png;base64,{base64.b64encode(png_bytes(color=color)).decode()}"
        for color in ("red", "green", "blue")
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.x.ai/v1/images/edits"
        payload = json.loads(request.content)
        assert "image" not in payload
        assert payload["images"] == [{"type": "image_url", "url": url} for url in source_urls]
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png_bytes()).decode()}]})

    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(
        provider="xai_grok_oauth",
        model="grok-imagine-image-2.0",
        prompt_text="Combine these references",
        parameters={"input_images": [
            {"source": "uploaded", "name": f"source-{index}.png", "data_url": url}
            for index, url in enumerate(source_urls)
        ]},
    ))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = XaiGrokOAuthProvider(auth_store=store, http_client=http_client).run_job(library, job.id)

    assert result.status == "succeeded"
    assert result.metadata["quality"] == "medium"
    assert result.metadata["resolution"] == "1k"
    assert result.metadata["input_image_count"] == 3


def test_grok_provider_rejects_more_than_three_edit_images_before_http(tmp_path):
    from backend.services.generation_jobs import GenerationJobConflict

    library = tmp_path / "library"
    source_url = f"data:image/png;base64,{base64.b64encode(png_bytes()).decode()}"

    repo = GenerationJobRepository(library)
    with pytest.raises(GenerationJobConflict, match="up to 3 input images"):
        repo.create_job(GenerationJobCreate(
            provider="xai_grok_oauth",
            model="grok-imagine-image-2.0",
            prompt_text="Combine four references",
            parameters={"input_images": [
                {"source": "uploaded", "name": f"source-{index}.png", "data_url": source_url}
                for index in range(4)
            ]},
        ))


def test_grok_status_api_lists_provider_and_disconnects_only_grok_store(tmp_path):
    from backend.services.xai_grok_oauth import GrokOAuthAuthStore

    store = GrokOAuthAuthStore()
    store.save_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})
    client = TestClient(create_app(library_path=tmp_path / "library"))

    providers = client.get("/api/generation-providers").json()
    grok = next(provider for provider in providers if provider["provider"] == "xai_grok_oauth")
    assert grok["authenticated"] is True
    response = client.post("/api/generation-providers/xai-grok-oauth/auth/disconnect")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert store.path.exists() is False
