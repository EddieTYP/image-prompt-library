from datetime import datetime, timedelta, timezone
from io import BytesIO
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Event
import time

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.db import connect
from backend.main import create_app
from backend.schemas import GenerationJobCreate, ItemCreate, PromptIn
from backend.services.generation_jobs import (
    GenerationJobConflict,
    GenerationJobRepository,
    _classify_error,
    sanitize_generation_error,
)


def png_bytes(color="orange", size=(18, 12)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool = True) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        ("Policy violated: request was refused by the safety system", "policy_violation"),
        ("429 too many requests; retry later", "rate_limited"),
        ("rate_limit_exceeded", "rate_limited"),
        ("rate-limit-exceeded", "rate_limited"),
        ("Token refresh is temporarily unavailable", "provider_unavailable"),
        ("401 authentication required; reconnect the provider", "auth_required"),
        ("Authentication refused: access_token expired", "auth_required"),
        ("Authorization refused with HTTP 401", "auth_required"),
        ("invalid_api_key: permission denied", "auth_required"),
        ("403 forbidden: request violates safety policy", "policy_violation"),
        ("Codex Responses API returned status 500", "provider_unavailable"),
        ("504 Gateway Timeout", "provider_unavailable"),
        ("The provider returned an opaque failure", "unknown"),
    ),
)
def test_generation_failure_classification(message, expected):
    assert _classify_error(message) == expected


@pytest.mark.parametrize(
    "message",
    (
        "Bearer secret-token",
        "AUTHORIZATION: secret-token",
        "token=opaque-value",
        "ACCESS_TOKEN=secret-token",
        "refresh_token=secret-token",
        "Id_Token=secret-token",
        "authorization_code=secret-token",
        "CODE_VERIFIER=secret-token",
        "device_auth_id=secret-token",
        "USER_CODE=secret-token",
        "api_key=sk-test-123456",
        "secret=opaque-value",
        "cookie=session-secret",
        "session=opaque-secret",
        "client_secret=secret-token",
        "accessToken=secret-token",
        "deviceAuthId=secret-token",
        "user-code=secret-token",
        "oauth_token=secret-token",
        "client-id=secret-token",
        "credentials=secret-token",
        '{"privateKey":"secret-token"}',
        '{"error":"clientSecret=secret-token"}',
        '{"outer":{"message":"access_token=secret-token"}}',
        '{"outer":"{\\"error\\":\\"clientSecret=secret-token\\"}"}',
        '{"outer":"{\\"clientSecret\\":\\"secret-token\\"}"}',
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue",
    ),
)
def test_generation_error_sanitizer_redacts_credential_markers_case_insensitively(message):
    sanitized = sanitize_generation_error(message)

    assert sanitized == "Generation failed; provider returned a credential-related error"
    assert "secret-token" not in sanitized


def test_generation_error_sanitizer_preserves_safe_token_status_message():
    message = "Token refresh is temporarily unavailable"

    assert sanitize_generation_error(message) == message


def test_generation_error_sanitizer_handles_deep_structured_text_without_parsing_it():
    message = "{" + '"context":{' * 500 + "0" + "}" * 500

    assert sanitize_generation_error(message) == message[:1000]


def test_generation_failure_classifies_raw_error_before_sanitizing(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="busy prompt"))

    failed = repo.mark_failed(job.id, "429 access_token=super-secret")

    assert failed.metadata["error_kind"] == "rate_limited"
    assert failed.error == "Generation failed; provider returned a credential-related error"
    assert "super-secret" not in failed.error


def test_generation_failure_never_persists_camel_case_provider_credentials(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="provider error boundary"))

    failed = repo.mark_failed(job.id, '{"error":"clientSecret=secret-canary"}')

    assert failed.error == "Generation failed; provider returned a credential-related error"
    with connect(tmp_path / "library") as conn:
        stored = conn.execute("SELECT error FROM generation_jobs WHERE id=?", (job.id,)).fetchone()[0]
    assert "secret-canary" not in stored


def create_source_item(c, *, author=None):
    payload = {
        "title": "Source prompt",
        "prompts": [{"language": "en", "text": "A cinematic moonlit robot", "is_original": True}],
    }
    if author is not None:
        payload["author"] = author
    return c.post("/api/items", json=payload).json()


def _make_running_job(tmp_path, *, started_minutes_ago: int):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="stale prompt"))
    running = repo.mark_running(job.id)
    started = (datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)).isoformat()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET started_at=?, updated_at=? WHERE id=?",
            (started, started, running.id),
        )
        conn.commit()
    return repo, running.id


def test_generation_job_can_stage_result_and_accept_into_source_item(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)

    created = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "manual_upload",
        "model": "manual-test-model",
        "prompt_language": "en",
        "prompt_text": "A cinematic moonlit robot",
        "edited_prompt_text": "A cinematic moonlit robot holding a lantern",
        "parameters": {"aspect_ratio": "1:1", "quality": "high"},
    })
    assert created.status_code == 200
    job = created.json()
    assert job["status"] == "queued"
    assert job["source_item_id"] == source_item["id"]
    assert job["provider"] == "manual_upload"
    assert job["parameters"]["aspect_ratio"] == "1:1"

    result = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes(), "image/png")},
        data={"metadata": '{"seed": 123}'},
    )
    assert result.status_code == 200
    succeeded = result.json()
    assert succeeded["status"] == "succeeded"
    assert succeeded["result_path"].startswith(f"generation-results/{job['id']}/")
    assert (tmp_path / "library" / succeeded["result_path"]).is_file()
    assert succeeded["result_width"] == 18
    assert succeeded["result_height"] == 12
    assert succeeded["result_sha256"]
    assert succeeded["metadata"]["seed"] == 123

    listed = c.get("/api/generation-jobs").json()
    assert listed["total"] == 1
    assert listed["jobs"][0]["id"] == job["id"]

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept")
    assert accepted.status_code == 200
    accepted_payload = accepted.json()
    assert accepted_payload["job"]["status"] == "accepted"
    item = accepted_payload["item"]
    assert item["id"] == source_item["id"]
    assert item["images"][0]["role"] == "result_image"
    assert item["images"][0]["original_path"].startswith("originals/")
    assert item["images"][0]["thumb_path"].startswith("thumbs/")
    assert item["images"][0]["preview_path"].startswith("previews/")

    assert c.post(f"/api/generation-jobs/{job['id']}/accept").status_code == 409


def test_generation_job_list_and_detail_redact_input_image_data_urls(tmp_path):
    c = client(tmp_path)
    payload_data = png_bytes("red", (4, 4))
    created = c.post(
        "/api/generation-jobs",
        json={
            "prompt_text": "Redaction regression",
            "parameters": {
                "input_images": [
                    {
                        "name": "seed.png",
                        "data_url": f"data:image/png;base64,{base64.b64encode(payload_data).decode()}",
                    }
                ],
            },
        },
    ).json()

    created_input = created["parameters"]["input_images"][0]
    assert "data_url" not in created_input
    assert created_input["has_data_url"] is True
    assert created_input["data_url_redacted"] is True
    assert created_input["name"] == "seed.png"

    detail = c.get(f"/api/generation-jobs/{created['id']}").json()
    detail_input = detail["parameters"]["input_images"][0]
    assert "data_url" not in detail_input
    assert detail_input["has_data_url"] is True
    assert detail_input["data_url_redacted"] is True

    listed = c.get("/api/generation-jobs").json()
    assert listed["total"] == 1
    listed_input = listed["jobs"][0]["parameters"]["input_images"][0]
    assert "data_url" not in listed_input
    assert listed_input["has_data_url"] is True
    assert listed_input["data_url_redacted"] is True


def test_generation_job_credentials_never_enter_storage_or_api_payloads(tmp_path):
    c = client(tmp_path)
    created = c.post(
        "/api/generation-jobs",
        json={
            "prompt_text": "Credential boundary regression",
            "parameters": {
                "quality": "high",
                "tokenValue": "token-secret",
                "authorizationValue": "authorization-secret",
                "clientIdValue": "client-secret",
                "APIKey": "api-key-secret",
                "apiKEYValue": "api-key-value-secret",
                "clientIDValue": "client-id-secret",
                "sessionid": "session-secret",
                "authorizationcode": "authorization-code-secret",
                "userCode": "device-user-code-secret",
                "jwtValue": "jwt-secret",
                "api_key_mode": "api-key-mode-secret",
                "clientSecretMode": "client-secret-mode-secret",
                "authorization_type": "authorization-type-secret",
                "password_style": "password-style-secret",
                "jwt_name": "jwt-name-secret",
                "access_token_count": 999,
                "apiKeyId": "api-key-id-secret",
                "apiKeyVerifier": "api-key-verifier-secret",
                "accessTokenId": "access-token-id-secret",
                "authorizationCodeId": "authorization-code-id-secret",
                "clientSecretId": "client-secret-id-secret",
                "xApiKeyId": "prefixed-api-key-id-secret",
                "secretKey": "secret-key-secret",
                "sessionIDCode": "session-id-code-secret",
                "auth_mode": "codex_oauth_native",
                "token_budget": 128,
                "token_count": 64,
                "header_style": "compact",
                "note": "access_token=credential-canary",
                "safe_note": "authorization settings are managed outside the library",
                "attachment_label": "Bearer image",
                "debug_messages": ["Bearer nested-secret-token", "kept"],
                "nested": {
                    "headers": {"Authorization": "Bearer header-secret"},
                    "cookies": "cookie-secret",
                    "safe": "kept",
                },
            },
        },
    )

    assert created.status_code == 200
    job = created.json()
    assert job["parameters"] == {
        "quality": "high",
        "auth_mode": "codex_oauth_native",
        "token_budget": 128,
        "token_count": 64,
        "header_style": "compact",
        "note": "[redacted credential data]",
        "safe_note": "authorization settings are managed outside the library",
        "attachment_label": "Bearer image",
        "debug_messages": ["[redacted credential data]", "kept"],
        "nested": {"safe": "kept"},
    }
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["parameters"] == job["parameters"]
    assert c.get("/api/generation-jobs").json()["jobs"][0]["parameters"] == job["parameters"]
    assert GenerationJobRepository(tmp_path / "library").get_job(job["id"]).parameters == job["parameters"]
    with connect(tmp_path / "library") as conn:
        stored = conn.execute("SELECT parameters FROM generation_jobs WHERE id=?", (job["id"],)).fetchone()[0]
    assert "credential-canary" not in stored


def test_generation_job_api_hides_internal_acceptance_metadata(tmp_path):
    c = client(tmp_path)
    created = c.post(
        "/api/generation-jobs",
        json={"prompt_text": "Internal metadata redaction"},
    ).json()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=? WHERE id=?",
            (
                json.dumps({
                    "visible": "kept",
                    "_generation_accept_claim": "private-claim",
                    "_generation_accept_claim_at": "private-timestamp",
                    "_generation_accept_artifacts": {"item_id": "private-item"},
                }),
                created["id"],
            ),
        )
        conn.commit()

    detail_metadata = c.get(f"/api/generation-jobs/{created['id']}").json()["metadata"]
    listed_metadata = c.get("/api/generation-jobs").json()["jobs"][0]["metadata"]

    assert detail_metadata == {"visible": "kept"}
    assert listed_metadata == {"visible": "kept"}


def test_generation_job_api_recursively_redacts_image_data(tmp_path):
    c = client(tmp_path)
    created = c.post(
        "/api/generation-jobs",
        json={
            "prompt_text": "Nested image redaction",
            "parameters": {
                "nested": {
                    "dataUrl": "data:image/png;base64,private-nested-data",
                    "image_url": "https://example.invalid/private-image.png",
                    "safe": "kept",
                },
            },
        },
    )

    assert created.status_code == 200
    job = created.json()
    assert job["parameters"] == {"nested": {"safe": "kept"}}
    stored = GenerationJobRepository(tmp_path / "library").get_job(job["id"])
    assert stored.parameters["nested"]["dataUrl"].startswith("data:image/")
    assert stored.parameters["nested"]["image_url"].startswith("https://")


def test_generation_result_media_is_servable_before_accept(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "prompt_text": "A cinematic moonlit robot",
    }).json()
    result = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("green"), "image/png")},
    ).json()

    media = c.get(f"/media/{result['result_path']}")

    assert media.status_code == 200
    assert media.headers["content-type"] == "image/png"


def test_generation_job_can_accept_result_as_new_variant_item(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "manual_upload",
        "model": "manual-test-model",
        "prompt_language": "en",
        "prompt_text": "A cinematic moonlit robot",
        "edited_prompt_text": "A cinematic moonlit robot holding a lantern",
        "parameters": {"aspect_ratio": "1:1"},
    }).json()
    c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("purple"), "image/png")},
    )

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["job"]["status"] == "accepted"
    new_item = payload["item"]
    assert new_item["id"] != source_item["id"]
    assert new_item["title"].startswith("Source prompt")
    assert new_item["images"][0]["id"] == payload["job"]["accepted_image_id"]
    assert new_item["images"][0]["role"] == "result_image"
    assert new_item["prompts"][0]["text"] == "A cinematic moonlit robot holding a lantern"
    assert new_item["prompts"][0]["is_original"] is True
    provenance = new_item["prompts"][0]["provenance"]
    assert provenance["kind"] == "generation_variant"
    assert provenance["source_item_id"] == source_item["id"]
    assert provenance["source_generation_job_id"] == job["id"]
    assert provenance["provider"] == "manual_upload"
    assert provenance["model"] == "manual-test-model"

    original_after = c.get(f"/api/items/{source_item['id']}").json()
    assert original_after["images"] == []


def test_accept_as_new_item_defaults_author_to_current_local_user_not_source_author(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c, author="Original Artist")
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "manual_upload",
        "model": "manual-test-model",
        "prompt_language": "en",
        "prompt_text": "A cinematic moonlit robot",
    }).json()
    c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("purple"), "image/png")},
    )

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert accepted.status_code == 200
    new_item = accepted.json()["item"]
    assert new_item["author"] == "User"
    assert new_item["author"] != source_item["author"]


def test_accept_as_new_item_uses_metadata_overrides_and_keeps_provenance(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "manual_upload",
        "model": "manual-test-model",
        "prompt_language": "en",
        "prompt_text": "Original generated prompt",
        "parameters": {"quality": "high"},
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("pink"), "image/png")})

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item", json={
        "title": "Edited generated title",
        "cluster_name": "Generated Drafts",
        "tags": ["edited", "variant"],
        "model": "edited-model-label",
        "source_name": "Edited source",
        "author": "Edward",
        "notes": "Edited notes before save.",
        "prompts": [{"language": "en", "text": "Edited prompt before save", "is_primary": True, "is_original": True}],
    })

    assert accepted.status_code == 200
    item = accepted.json()["item"]
    assert item["title"] == "Edited generated title"
    assert item["cluster"]["name"] == "Generated Drafts"
    assert item["model"] == "edited-model-label"
    assert item["source_name"] == "Edited source"
    assert item["author"] == "Edward"
    assert item["notes"] == "Edited notes before save."
    assert {tag["name"] for tag in item["tags"]} == {"edited", "variant"}
    assert item["prompts"][0]["text"] == "Edited prompt before save"
    provenance = item["prompts"][0]["provenance"]
    assert provenance["kind"] == "generation_variant"
    assert provenance["source_item_id"] == source_item["id"]
    assert provenance["source_generation_job_id"] == job["id"]
    assert provenance["provider"] == "manual_upload"
    assert provenance["model"] == "manual-test-model"
    assert provenance["mode"] == "text_to_image"
    assert provenance["parameters"] == {"quality": "high"}


def test_accept_as_new_item_redacts_private_generation_parameters_from_provenance(tmp_path):
    c = client(tmp_path)
    encoded = base64.b64encode(png_bytes("pink")).decode()
    job = c.post("/api/generation-jobs", json={
        "mode": "image_edit",
        "provider": "manual_upload",
        "prompt_language": "en",
        "prompt_text": "Private reference regression",
        "parameters": {
            "quality": "high",
            "api_key": "must-not-persist",
            "headers": {"Authorization": "Bearer header-secret"},
            "cookies": "cookie-secret",
            "auth": "auth-secret",
            "clientId": "client-id-secret",
            "tokenValue": "token-value-secret",
            "authorizationValue": "authorization-value-secret",
            "input_images": [{
                "name": "private-reference.png",
                "data_url": f"data:image/png;base64,{encoded}",
                "nested": {"refresh_token": "must-not-persist-either"},
            }],
        },
    }).json()
    c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    )

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert accepted.status_code == 200
    provenance = accepted.json()["item"]["prompts"][0]["provenance"]
    assert provenance["parameters"] == {
        "quality": "high",
        "input_images": [{"name": "private-reference.png", "nested": {}}],
    }
    serialized = json.dumps(provenance)
    assert encoded not in serialized
    assert "must-not-persist" not in serialized
    assert "header-secret" not in serialized
    assert "cookie-secret" not in serialized
    assert "auth-secret" not in serialized
    assert "client-id-secret" not in serialized
    assert "token-value-secret" not in serialized
    assert "authorization-value-secret" not in serialized


def test_accept_as_new_item_sanitizes_override_prompt_provenance(tmp_path):
    c = client(tmp_path)
    job = c.post(
        "/api/generation-jobs",
        json={"provider": "manual_upload", "prompt_text": "Override provenance regression"},
    ).json()
    c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    )

    accepted = c.post(
        f"/api/generation-jobs/{job['id']}/accept-as-new-item",
        json={
            "prompts": [{
                "language": "en",
                "text": "Edited safe prompt",
                "provenance": {
                    "safe_note": "kept",
                    "tokenValue": "token-secret",
                    "authorization": "authorization-secret",
                    "nested": {"cookies": "cookie-secret", "safe": "kept"},
                },
            }],
        },
    )

    assert accepted.status_code == 200
    provenance = accepted.json()["item"]["prompts"][0]["provenance"]
    assert provenance["safe_note"] == "kept"
    assert provenance["nested"] == {"safe": "kept"}
    serialized = json.dumps(provenance)
    assert "token-secret" not in serialized
    assert "authorization-secret" not in serialized
    assert "cookie-secret" not in serialized


def test_standalone_generation_job_can_save_as_new_item(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={
        "mode": "text_to_image",
        "provider": "manual_upload",
        "model": "standalone-model",
        "prompt_language": "en",
        "prompt_text": "A standalone glowing library",
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("cyan"), "image/png")})

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item", json={"title": "Standalone generated item"})

    assert accepted.status_code == 200
    item = accepted.json()["item"]
    assert item["title"] == "Standalone generated item"
    assert item["images"][0]["role"] == "result_image"
    provenance = item["prompts"][0]["provenance"]
    assert provenance["kind"] == "generation_standalone"
    assert provenance["source_item_id"] is None
    assert provenance["source_generation_job_id"] == job["id"]


def test_generation_failure_classifies_policy_and_rate_limit_errors(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    policy_job = c.post("/api/generation-jobs", json={"source_item_id": source_item["id"], "prompt_text": "blocked prompt"}).json()
    rate_job = c.post("/api/generation-jobs", json={"source_item_id": source_item["id"], "prompt_text": "busy prompt"}).json()
    repo = GenerationJobRepository(tmp_path / "library")

    policy_failed = repo.mark_failed(policy_job["id"], "Policy violated: request was refused by safety system")
    rate_failed = repo.mark_failed(rate_job["id"], "429 too many requests, retry later")

    assert policy_failed.metadata["error_kind"] == "policy_violation"
    assert rate_failed.metadata["error_kind"] == "rate_limited"


def test_generation_job_discard_does_not_attach_result(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "prompt_text": "A cinematic moonlit robot",
    }).json()
    c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    )

    discarded = c.post(f"/api/generation-jobs/{job['id']}/discard")

    assert discarded.status_code == 200
    assert discarded.json()["status"] == "discarded"
    item = c.get(f"/api/items/{source_item['id']}").json()
    assert item["images"] == []
    assert c.post(f"/api/generation-jobs/{job['id']}/accept").status_code == 409


def test_generation_job_discard_deletes_transient_result_file_and_hides_path(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "prompt_text": "A cinematic moonlit robot",
    }).json()
    result = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    ).json()
    result_file = tmp_path / "library" / result["result_path"]
    assert result_file.is_file()

    discarded = c.post(f"/api/generation-jobs/{job['id']}/discard")

    assert discarded.status_code == 200
    payload = discarded.json()
    assert payload["status"] == "discarded"
    assert payload["result_path"] is None
    assert not result_file.exists()


def test_generation_job_discard_rejects_accepted_or_unsafe_result_paths(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    saved = c.post("/api/generation-jobs", json={"source_item_id": source_item["id"], "prompt_text": "saved"}).json()
    c.post(f"/api/generation-jobs/{saved['id']}/result", files={"file": ("generated.png", png_bytes("red"), "image/png")})
    c.post(f"/api/generation-jobs/{saved['id']}/accept")
    assert c.post(f"/api/generation-jobs/{saved['id']}/discard").status_code == 409

    unsafe = c.post("/api/generation-jobs", json={"source_item_id": source_item["id"], "prompt_text": "unsafe"}).json()
    c.post(f"/api/generation-jobs/{unsafe['id']}/result", files={"file": ("generated.png", png_bytes("yellow"), "image/png")})
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET result_path=? WHERE id=?", ("originals/not-transient.png", unsafe["id"]))
        conn.commit()

    response = c.post(f"/api/generation-jobs/{unsafe['id']}/discard")

    assert response.status_code == 409
    assert "transient" in response.json()["detail"].lower() or "safe" in response.json()["detail"].lower()


def test_generation_job_clones_generation_result_inputs_so_source_stays_discardable(tmp_path, monkeypatch):
    c = client(tmp_path)

    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda library_path, *, provider: None)

    source = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "first draft",
    }).json()
    c.post(
        f"/api/generation-jobs/{source['id']}/result",
        files={"file": ("source.png", png_bytes("blue"), "image/png")},
    )
    source = c.get(f"/api/generation-jobs/{source['id']}").json()
    source_path = source["result_path"]

    downstream = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "refine first draft",
        "parameters": {
            "input_images": [{"result_path": source_path, "name": "source.png"}],
        },
    }).json()

    cloned_input = downstream["parameters"]["input_images"][0]
    assert cloned_input["result_path"] != source_path
    assert cloned_input["result_path"].startswith(f"generation-references/{downstream['id']}/")
    assert (tmp_path / "library" / cloned_input["result_path"]).is_file()
    assert (tmp_path / "library" / cloned_input["result_path"]).read_bytes() == (tmp_path / "library" / source_path).read_bytes()
    assert downstream["metadata"]["reference_image_copies"][0]["source_generation_job_id"] == source["id"]
    assert downstream["metadata"]["reference_image_copies"][0]["source_result_path"] == source_path
    assert downstream["metadata"]["reference_image_copies"][0]["copied_path"] == cloned_input["result_path"]

    discard = c.post(f"/api/generation-jobs/{source['id']}/discard")
    assert discard.status_code == 200
    assert discard.json()["status"] == "discarded"
    assert not (tmp_path / "library" / source_path).exists()
    assert (tmp_path / "library" / cloned_input["result_path"]).is_file()


def test_generation_job_uses_ordered_library_image_references_without_duplicate_attach(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    first = c.post(
        f"/api/items/{source_item['id']}/images",
        files={"file": ("first.png", png_bytes("red"), "image/png")},
        data={"role": "result_image"},
    ).json()
    second = c.post(
        f"/api/items/{source_item['id']}/images",
        files={"file": ("second.png", png_bytes("blue"), "image/png")},
        data={"role": "reference_image"},
    ).json()

    response = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "Use both saved references",
        "parameters": {"input_images": [
            {"source": "library", "image_id": second["id"], "name": "Second"},
            {"source": "library", "image_id": first["id"], "name": "First"},
        ]},
    })

    assert response.status_code == 200
    job = response.json()
    assert job["reference_image_ids"] == [second["id"], first["id"]]
    assert [image["image_id"] for image in job["parameters"]["input_images"]] == [second["id"], first["id"]]
    assert [image["role"] for image in job["parameters"]["input_images"]] == ["reference_image", "result_image"]
    assert c.get(f"/media/{job['parameters']['input_images'][0]['preview_path']}").status_code == 200

    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("green"), "image/png")})
    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept")

    assert accepted.status_code == 200
    images = accepted.json()["item"]["images"]
    assert len(images) == 3
    assert {image["id"] for image in images}.issuperset({first["id"], second["id"]})


def test_generation_job_attach_copies_library_reference_from_another_item(tmp_path):
    c = client(tmp_path)
    target_item = create_source_item(c)
    reference_item = create_source_item(c)
    reference = c.post(
        f"/api/items/{reference_item['id']}/images",
        files={"file": ("external-reference.png", png_bytes("purple"), "image/png")},
        data={"role": "reference_image"},
    ).json()
    job = c.post("/api/generation-jobs", json={
        "source_item_id": target_item["id"],
        "provider": "manual_upload",
        "prompt_text": "Use a reference from another item",
        "parameters": {"input_images": [{"source": "library", "image_id": reference["id"], "name": "External reference"}]},
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("green"), "image/png")})

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept")

    assert accepted.status_code == 200
    images = accepted.json()["item"]["images"]
    assert [image["role"] for image in images] == ["result_image", "reference_image"]
    assert images[1]["id"] != reference["id"]


def test_generation_job_rejects_missing_library_reference(tmp_path):
    c = client(tmp_path)

    response = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "Missing reference",
        "parameters": {"input_images": [{"source": "library", "image_id": "img_missing"}]},
    })

    assert response.status_code == 409
    assert "not found" in response.json()["detail"].lower()


def test_generation_job_uses_preserved_library_clone_when_image_is_missing(tmp_path):
    c = client(tmp_path)
    clone_path = tmp_path / "library" / "generation-references" / "old-job" / "reference.png"
    clone_path.parent.mkdir(parents=True, exist_ok=True)
    clone_path.write_bytes(png_bytes("purple"))

    response = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "Use the preserved reference clone",
        "parameters": {"input_images": [{
            "source": "library",
            "image_id": "img_deleted",
            "result_path": "generation-references/old-job/reference.png",
            "name": "Preserved reference",
        }]},
    })

    assert response.status_code == 200
    assert response.json()["parameters"]["input_images"][0]["result_path"] == "generation-references/old-job/reference.png"


def test_generation_job_save_as_new_copies_library_reference_and_keeps_provenance(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    reference = c.post(
        f"/api/items/{source_item['id']}/images",
        files={"file": ("reference.png", png_bytes("purple"), "image/png")},
        data={"role": "reference_image"},
    ).json()
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "Save with its reference",
        "parameters": {"input_images": [{"source": "library", "image_id": reference["id"], "name": "Source prompt"}]},
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("green"), "image/png")})

    accepted = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert accepted.status_code == 200
    item = accepted.json()["item"]
    assert [image["role"] for image in item["images"]] == ["result_image", "reference_image"]
    provenance = item["prompts"][0]["provenance"]
    assert provenance["source_generation_job_id"] == job["id"]
    assert provenance["parameters"]["input_images"][0]["image_id"] == reference["id"]


def test_generation_job_rejects_more_than_four_mixed_inputs(tmp_path):
    c = client(tmp_path)
    image_data_url = "data:image/png;base64," + base64.b64encode(png_bytes()).decode()

    response = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "Too many references",
        "parameters": {"input_images": [
            {"source": "uploaded", "name": f"reference-{index}.png", "data_url": image_data_url}
            for index in range(5)
        ]},
    })

    assert response.status_code == 409
    assert "up to 4" in response.json()["detail"]


def test_generation_job_rejects_unsafe_result_path_inputs_on_create(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)

    unsafe_paths = [
        "/tmp/secret.png",
        "../secret.png",
        "originals/not-a-generation-reference.png",
        "generation-results/missing-job/missing.png",
    ]
    for result_path in unsafe_paths:
        response = c.post("/api/generation-jobs", json={
            "source_item_id": source_item["id"],
            "provider": "manual_upload",
            "prompt_text": "refine unsafe input",
            "parameters": {"input_images": [{"result_path": result_path, "name": "unsafe.png"}]},
        })

        assert response.status_code == 409
        assert "input image" in response.json()["detail"].lower()

    bad_image = tmp_path / "library" / "generation-results" / "gen_source" / "not-image.png"
    bad_image.parent.mkdir(parents=True, exist_ok=True)
    bad_image.write_text("not really an image", encoding="utf-8")
    response = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "refine invalid image input",
        "parameters": {"input_images": [{"result_path": "generation-results/gen_source/not-image.png", "name": "not-image.png"}]},
    })

    assert response.status_code == 409
    assert "input image" in response.json()["detail"].lower()


def test_generation_job_rejects_symlinked_generation_root_inputs_on_create(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    outside_root = tmp_path / "outside-results"
    outside_image = outside_root / "gen_source" / "source.png"
    outside_image.parent.mkdir(parents=True)
    outside_image.write_bytes(png_bytes("red"))
    symlink_or_skip(tmp_path / "library" / "generation-results", outside_root)

    response = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "refine symlinked input",
        "parameters": {"input_images": [{"result_path": "generation-results/gen_source/source.png", "name": "source.png"}]},
    })

    assert response.status_code == 409
    assert "input image" in response.json()["detail"].lower()
    assert outside_image.is_file()


def test_generation_job_rejects_in_library_symlinked_generation_roots_on_create(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    library = tmp_path / "library"
    wrong_results = library / "wrong-results"
    wrong_results_image = wrong_results / "gen_source" / "source.png"
    wrong_results_image.parent.mkdir(parents=True)
    wrong_results_image.write_bytes(png_bytes("red"))
    symlink_or_skip(library / "generation-results", wrong_results)

    response = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "refine symlinked in-library result root",
        "parameters": {"input_images": [{"result_path": "generation-results/gen_source/source.png", "name": "source.png"}]},
    })

    assert response.status_code == 409
    assert wrong_results_image.is_file()

    (library / "generation-results").unlink()
    wrong_references = library / "wrong-references"
    wrong_reference_image = wrong_references / "gen_source" / "source.png"
    wrong_reference_image.parent.mkdir(parents=True)
    wrong_reference_image.write_bytes(png_bytes("green"))
    symlink_or_skip(library / "generation-references", wrong_references)

    response = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "refine symlinked in-library reference root",
        "parameters": {"input_images": [{"result_path": "generation-references/gen_source/source.png", "name": "source.png"}]},
    })

    assert response.status_code == 409
    assert wrong_reference_image.is_file()


def test_stage_result_rejects_symlinked_generation_result_root_before_write(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "unsafe result write"}).json()
    outside_root = tmp_path / "outside-results"
    outside_root.mkdir()
    symlink_or_skip(tmp_path / "library" / "generation-results", outside_root)

    response = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("green"), "image/png")},
    )

    assert response.status_code == 409
    assert list(outside_root.rglob("*")) == []
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["status"] == "queued"


def test_stage_result_rejects_generation_result_root_alias_to_library(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "unsafe root alias"}).json()
    library = tmp_path / "library"
    symlink_or_skip(library / "generation-results", library)

    response = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("green"), "image/png")},
    )

    assert response.status_code == 409
    assert not (library / job["id"]).exists()
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["status"] == "queued"


def test_stage_result_rejects_nested_generation_result_symlink_before_write(tmp_path):
    c = client(tmp_path)
    existing = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "existing result"}).json()
    c.post(f"/api/generation-jobs/{existing['id']}/result", files={"file": ("existing.png", png_bytes("blue"), "image/png")})
    existing_dir = tmp_path / "library" / "generation-results" / existing["id"]
    before = sorted(path.relative_to(existing_dir).as_posix() for path in existing_dir.rglob("*"))
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "unsafe nested result write"}).json()
    symlink_or_skip(tmp_path / "library" / "generation-results" / job["id"], existing_dir)

    response = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("green"), "image/png")},
    )

    assert response.status_code == 409
    assert sorted(path.relative_to(existing_dir).as_posix() for path in existing_dir.rglob("*")) == before
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["status"] == "queued"


def test_generation_job_rejects_symlinked_generation_reference_clone_destination(tmp_path):
    c = client(tmp_path)
    source = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "source result"}).json()
    c.post(f"/api/generation-jobs/{source['id']}/result", files={"file": ("source.png", png_bytes("blue"), "image/png")})
    source_path = c.get(f"/api/generation-jobs/{source['id']}").json()["result_path"]
    outside_root = tmp_path / "outside-references"
    outside_root.mkdir()
    symlink_or_skip(tmp_path / "library" / "generation-references", outside_root)

    response = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "clone into unsafe reference root",
        "parameters": {"input_images": [{"result_path": source_path, "name": "source.png"}]},
    })

    assert response.status_code == 409
    assert list(outside_root.rglob("*")) == []


def test_generation_job_rejects_nested_generation_reference_clone_symlink_destination(tmp_path):
    from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository

    c = client(tmp_path)
    source = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "source result"}).json()
    c.post(f"/api/generation-jobs/{source['id']}/result", files={"file": ("source.png", png_bytes("blue"), "image/png")})
    source_path = c.get(f"/api/generation-jobs/{source['id']}").json()["result_path"]
    library = tmp_path / "library"
    wrong_reference_dir = library / "generation-references" / "other-job"
    wrong_reference_dir.mkdir(parents=True)
    symlink_or_skip(library / "generation-references" / "dest-job", wrong_reference_dir)

    try:
        GenerationJobRepository(library)._clone_generation_result_input(job_id="dest-job", result_path=source_path)
    except GenerationJobConflict:
        pass
    else:
        raise AssertionError("expected nested reference symlink clone destination to be rejected")

    assert list(wrong_reference_dir.rglob("*")) == []


def test_generation_reference_clone_recovers_partial_deterministic_destination(tmp_path):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="source result"))
    source = repo.stage_result(source.id, png_bytes("blue"), "source.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="downstream"))
    clone_path = (
        library
        / "generation-references"
        / downstream.id
        / f"from-{source.id}-{source.result_sha256[:12]}.png"
    )
    clone_path.parent.mkdir(parents=True)
    clone_path.write_bytes(b"partial")

    copied_path, _ = repo._clone_generation_result_input(
        job_id=downstream.id,
        result_path=source.result_path,
        name="source.png",
    )

    assert copied_path == clone_path.relative_to(library).as_posix()
    assert clone_path.read_bytes() == png_bytes("blue")
    assert list(clone_path.parent.glob("*.tmp")) == []


def test_discard_rejects_symlinked_generation_result_root_before_delete(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "unsafe symlink result"}).json()
    outside_root = tmp_path / "outside-results"
    outside_file = outside_root / job["id"] / "generated.png"
    outside_file.parent.mkdir(parents=True)
    outside_file.write_bytes(png_bytes("purple"))
    symlink_or_skip(tmp_path / "library" / "generation-results", outside_root)
    result_path = f"generation-results/{job['id']}/generated.png"
    with connect(tmp_path / "library") as conn:
        conn.execute(
            """UPDATE generation_jobs
               SET status='succeeded', result_path=?, result_width=18, result_height=12, result_sha256='abc'
               WHERE id=?""",
            (result_path, job["id"]),
        )
        conn.commit()

    response = c.post(f"/api/generation-jobs/{job['id']}/discard")

    assert response.status_code == 409
    assert outside_file.is_file()
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["status"] == "succeeded"


def test_discard_rejects_nested_generation_result_file_symlink_before_delete(tmp_path):
    c = client(tmp_path)
    target = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "target result"}).json()
    c.post(f"/api/generation-jobs/{target['id']}/result", files={"file": ("target.png", png_bytes("purple"), "image/png")})
    target = c.get(f"/api/generation-jobs/{target['id']}").json()
    target_file = tmp_path / "library" / target["result_path"]
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "symlinked victim result"}).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("victim.png", png_bytes("orange"), "image/png")})
    job = c.get(f"/api/generation-jobs/{job['id']}").json()
    victim_file = tmp_path / "library" / job["result_path"]
    victim_file.unlink()
    symlink_or_skip(victim_file, target_file, target_is_directory=False)

    response = c.post(f"/api/generation-jobs/{job['id']}/discard")

    assert response.status_code == 409
    assert target_file.is_file()
    assert victim_file.is_symlink()
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["status"] == "succeeded"


def test_accept_rejects_legacy_invalid_input_reference_without_mutating_source_item(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "accept invalid reference",
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("blue"), "image/png")})
    staged = c.get(f"/api/generation-jobs/{job['id']}").json()
    result_file = tmp_path / "library" / staged["result_path"]
    legacy_parameters = {"input_images": [{"result_path": "generation-results/missing-job/missing.png", "name": "missing.png"}]}
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), job["id"]))
        conn.commit()

    response = c.post(f"/api/generation-jobs/{job['id']}/accept")

    assert response.status_code == 409
    assert result_file.is_file()
    item = c.get(f"/api/items/{source_item['id']}").json()
    assert item["images"] == []
    after = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert after["status"] == "succeeded"
    assert after["accepted_image_id"] is None


def test_accept_as_new_rejects_legacy_invalid_input_reference_without_creating_item(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "accept invalid reference as new item",
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("blue"), "image/png")})
    staged = c.get(f"/api/generation-jobs/{job['id']}").json()
    result_file = tmp_path / "library" / staged["result_path"]
    legacy_parameters = {"input_images": [{"result_path": "generation-results/missing-job/missing.png", "name": "missing.png"}]}
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), job["id"]))
        conn.commit()
    initial_total = c.get("/api/items").json()["total"]

    response = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert response.status_code == 409
    assert result_file.is_file()
    assert c.get("/api/items").json()["total"] == initial_total
    assert c.get(f"/api/items/{source_item['id']}").json()["images"] == []
    after = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert after["status"] == "succeeded"
    assert after["accepted_image_id"] is None


def test_accept_as_new_rejects_result_changed_after_staging(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "staged result integrity",
    }).json()
    staged = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    ).json()
    result_file = tmp_path / "library" / staged["result_path"]
    result_file.write_bytes(png_bytes("purple"))
    initial_total = c.get("/api/items").json()["total"]

    response = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert response.status_code == 409
    assert "changed after it was staged" in response.json()["detail"]
    assert c.get("/api/items").json()["total"] == initial_total
    after = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert after["status"] == "succeeded"
    assert after["accepted_image_id"] is None
    assert result_file.read_bytes() == png_bytes("purple")


def test_accept_as_new_rejects_missing_result_integrity_record(tmp_path):
    c = client(tmp_path)
    job = c.post(
        "/api/generation-jobs",
        json={"provider": "manual_upload", "prompt_text": "missing staged integrity"},
    ).json()
    staged = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    ).json()
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET result_sha256=NULL WHERE id=?", (job["id"],))
        conn.commit()
    initial_total = c.get("/api/items").json()["total"]

    response = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert response.status_code == 409
    assert "integrity record is missing" in response.json()["detail"]
    assert c.get("/api/items").json()["total"] == initial_total
    assert (tmp_path / "library" / staged["result_path"]).is_file()


def test_accept_rejects_invalid_data_url_reference_without_mutating_source_item(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    bad_data_url = "data:image/png;base64," + base64.b64encode(b"not an image").decode()
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "accept invalid data url reference",
        "parameters": {"input_images": [{"data_url": bad_data_url, "name": "bad.png"}]},
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("blue"), "image/png")})
    staged = c.get(f"/api/generation-jobs/{job['id']}").json()
    result_file = tmp_path / "library" / staged["result_path"]

    response = c.post(f"/api/generation-jobs/{job['id']}/accept")

    assert response.status_code == 409
    assert result_file.is_file()
    assert c.get(f"/api/items/{source_item['id']}").json()["images"] == []
    after = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert after["status"] == "succeeded"
    assert after["accepted_image_id"] is None


def test_accept_rejects_malformed_data_url_reference_without_mutating_source_item(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "accept malformed data url reference",
        "parameters": {"input_images": [{"data_url": "https://example.invalid/image.png", "name": "bad.png"}]},
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("blue"), "image/png")})
    staged = c.get(f"/api/generation-jobs/{job['id']}").json()
    result_file = tmp_path / "library" / staged["result_path"]

    response = c.post(f"/api/generation-jobs/{job['id']}/accept")

    assert response.status_code == 409
    assert result_file.is_file()
    assert c.get(f"/api/items/{source_item['id']}").json()["images"] == []
    after = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert after["status"] == "succeeded"
    assert after["accepted_image_id"] is None


def test_accept_as_new_prevalidates_storeable_result_before_creating_item(tmp_path, monkeypatch):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "oversized accept as new",
    }).json()
    c.post(f"/api/generation-jobs/{job['id']}/result", files={"file": ("generated.png", png_bytes("blue"), "image/png")})
    staged = c.get(f"/api/generation-jobs/{job['id']}").json()
    result_file = tmp_path / "library" / staged["result_path"]
    initial_total = c.get("/api/items").json()["total"]
    monkeypatch.setattr("backend.services.generation_jobs.MAX_IMAGE_PIXELS", 1)

    response = c.post(f"/api/generation-jobs/{job['id']}/accept-as-new-item")

    assert response.status_code == 409
    assert result_file.is_file()
    assert c.get("/api/items").json()["total"] == initial_total
    assert c.get(f"/api/items/{source_item['id']}").json()["images"] == []
    after = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert after["status"] == "succeeded"
    assert after["accepted_image_id"] is None


def test_discard_lazily_repairs_legacy_generation_job_references(tmp_path, monkeypatch):
    c = client(tmp_path)
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda library_path, *, provider: None)

    source = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "legacy source"}).json()
    c.post(f"/api/generation-jobs/{source['id']}/result", files={"file": ("source.png", png_bytes("blue"), "image/png")})
    source = c.get(f"/api/generation-jobs/{source['id']}").json()
    source_path = source["result_path"]

    downstream = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "legacy downstream"}).json()
    legacy_parameters = {
        "input_images": [{"result_path": source_path, "preview_path": source_path, "name": "legacy-source.png"}]
    }
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), downstream["id"]))
        conn.commit()

    response = c.post(f"/api/generation-jobs/{source['id']}/discard")

    assert response.status_code == 200
    discarded = response.json()
    assert discarded["status"] == "discarded"
    assert not (tmp_path / "library" / source_path).exists()

    repaired = c.get(f"/api/generation-jobs/{downstream['id']}").json()
    repaired_spec = repaired["parameters"]["input_images"][0]
    assert repaired_spec["result_path"] != source_path
    assert repaired_spec["preview_path"] == repaired_spec["result_path"]
    assert repaired_spec["result_path"].startswith(f"generation-references/{downstream['id']}/")
    assert (tmp_path / "library" / repaired_spec["result_path"]).is_file()
    assert repaired["metadata"]["reference_image_copies"][0]["source_result_path"] == source_path
    assert repaired["metadata"]["reference_image_repair"]["repaired_from_discard_job_id"] == source["id"]


def test_discard_status_conflict_does_not_repair_downstream_reference(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="discard race source"))
    source = repo.stage_result(source.id, png_bytes("black"), "source.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="discard race downstream"))
    legacy_parameters = {
        "input_images": [{"result_path": source.result_path, "preview_path": source.result_path, "name": "source.png"}]
    }
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), downstream.id))
        conn.commit()

    started = Event()
    release = Event()
    original_check = repo._result_path_is_discardable

    def gated_check(job):
        result = original_check(job)
        started.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(repo, "_result_path_is_discardable", gated_check)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(repo.discard_job, source.id)
        assert started.wait(5)
        with connect(tmp_path / "library") as conn:
            conn.execute("UPDATE generation_jobs SET status='failed' WHERE id=?", (source.id,))
            conn.commit()
        release.set()
        with pytest.raises(GenerationJobConflict):
            pending.result()

    assert repo.get_job(source.id).status == "failed"
    assert repo.get_job(downstream.id).parameters == legacy_parameters
    assert repo.get_job(downstream.id).metadata.get("reference_image_copies") is None


def test_discard_retry_status_conflict_does_not_repair_downstream_reference(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="retry race source"))
    source = repo.stage_result(source.id, png_bytes("silver"), "source.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="retry race downstream"))
    legacy_parameters = {"input_images": [{"result_path": source.result_path, "name": "source.png"}]}
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), downstream.id))
        conn.commit()

    started = Event()
    release = Event()
    original_check = repo._result_path_is_discardable

    def gated_check(job):
        result = original_check(job)
        started.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(repo, "_result_path_is_discardable", gated_check)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(repo.discard_and_retry_job, source.id)
        assert started.wait(5)
        with connect(tmp_path / "library") as conn:
            conn.execute("UPDATE generation_jobs SET status='failed' WHERE id=?", (source.id,))
            conn.commit()
        release.set()
        with pytest.raises(GenerationJobConflict):
            pending.result()

    assert repo.get_job(source.id).status == "failed"
    assert repo.get_job(downstream.id).parameters == legacy_parameters
    assert repo.get_job(downstream.id).metadata.get("reference_image_copies") is None


def test_discard_repair_and_failed_retry_snapshot_reference_before_source_cleanup(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="repair source"))
    source = repo.stage_result(source.id, png_bytes("olive"), "source.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="repair downstream"))
    legacy_parameters = {
        "input_images": [{"result_path": source.result_path, "preview_path": source.result_path, "name": "source.png"}]
    }
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET parameters=?, status='failed', error=? WHERE id=?",
            (json.dumps(legacy_parameters), "failed downstream", downstream.id),
        )
        conn.commit()

    started = Event()
    release = Event()
    original_repair = repo._repair_generation_job_references_to_result

    def gated_repair(job):
        started.set()
        assert release.wait(5)
        return original_repair(job)

    monkeypatch.setattr(repo, "_repair_generation_job_references_to_result", gated_repair)
    with ThreadPoolExecutor(max_workers=2) as pool:
        discard_future = pool.submit(repo.discard_job, source.id)
        assert started.wait(5)
        retry_future = pool.submit(repo.retry_failed_job, downstream.id)
        retry = retry_future.result()
        release.set()
        discarded = discard_future.result()

    retry_spec = retry.parameters["input_images"][0]
    assert discarded.status == "discarded"
    assert retry_spec["result_path"].startswith(f"generation-references/{retry.id}/")
    assert retry_spec["preview_path"] == retry_spec["result_path"]
    assert (tmp_path / "library" / retry_spec["result_path"]).is_file()
    assert not (tmp_path / "library" / source.result_path).exists()


def test_discard_repair_failure_leaves_pending_marker_for_idempotent_resume(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="pending source"))
    source = repo.stage_result(source.id, png_bytes("plum"), "source.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="pending downstream"))
    legacy_parameters = {"input_images": [{"result_path": source.result_path, "name": "source.png"}]}
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), downstream.id))
        conn.commit()

    original_repair = repo._repair_generation_job_references_to_result

    def fail_once(_job):
        raise GenerationJobConflict("repair unavailable")

    monkeypatch.setattr(repo, "_repair_generation_job_references_to_result", fail_once)
    with pytest.raises(GenerationJobConflict, match="repair unavailable"):
        repo.discard_job(source.id)

    pending = repo.get_job(source.id)
    assert pending.status == "discarded"
    assert pending.metadata["discard_repair_pending"] is True
    assert (tmp_path / "library" / source.result_path).is_file()

    monkeypatch.setattr(repo, "_repair_generation_job_references_to_result", original_repair)
    resumed = repo.discard_job(source.id)

    assert resumed.status == "discarded"
    assert resumed.metadata.get("discard_repair_pending") is None
    repaired = repo.get_job(downstream.id)
    repaired_path = repaired.parameters["input_images"][0]["result_path"]
    assert repaired_path.startswith(f"generation-references/{downstream.id}/")
    assert not (tmp_path / "library" / source.result_path).exists()


def test_concurrent_discards_merge_two_source_repairs_into_one_downstream_job(tmp_path):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    first = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="first source"))
    second = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="second source"))
    first = repo.stage_result(first.id, png_bytes("red"), "first.png")
    second = repo.stage_result(second.id, png_bytes("blue"), "second.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="two source downstream"))
    parameters = {
        "input_images": [
            {"result_path": first.result_path, "preview_path": first.result_path, "name": "first.png"},
            {"result_path": second.result_path, "preview_path": second.result_path, "name": "second.png"},
        ]
    }
    with connect(library) as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(parameters), downstream.id))
        conn.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        discarded = list(pool.map(repo.discard_job, [first.id, second.id]))

    assert {job.status for job in discarded} == {"discarded"}
    repaired_specs = repo.get_job(downstream.id).parameters["input_images"]
    assert all(spec["result_path"].startswith(f"generation-references/{downstream.id}/") for spec in repaired_specs)
    assert all(spec["preview_path"] == spec["result_path"] for spec in repaired_specs)
    assert not (library / first.result_path).exists()
    assert not (library / second.result_path).exists()


def test_discard_file_removal_failure_keeps_pending_repair_for_retry(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="locked result"))
    source = repo.stage_result(source.id, png_bytes("green"), "source.png")
    original_remove = repo._remove_discarded_result_file

    def fail_remove(_path):
        raise GenerationJobConflict("Generation result could not be removed. Retry the discard.")

    monkeypatch.setattr(repo, "_remove_discarded_result_file", fail_remove)
    with pytest.raises(GenerationJobConflict, match="could not be removed"):
        repo.discard_job(source.id)

    pending = repo.get_job(source.id)
    assert pending.metadata["discard_repair_pending"] is True
    assert (repo.library_path / source.result_path).is_file()

    monkeypatch.setattr(repo, "_remove_discarded_result_file", original_remove)
    resumed = repo.discard_job(source.id)
    assert resumed.metadata.get("discard_repair_pending") is None
    assert not (repo.library_path / source.result_path).exists()


def test_backend_restart_resumes_pending_discard_repair(tmp_path, monkeypatch):
    from backend.services.generation_queue import recover_interrupted_generation_jobs

    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    source = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="restart repair source"))
    source = repo.stage_result(source.id, png_bytes("navy"), "source.png")
    downstream = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="restart repair downstream"))
    legacy_parameters = {"input_images": [{"result_path": source.result_path, "name": "source.png"}]}
    with connect(library) as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), downstream.id))
        conn.commit()

    original_repair = GenerationJobRepository._repair_generation_job_references_to_result

    def fail_repair(_job):
        raise GenerationJobConflict("repair unavailable")

    monkeypatch.setattr(repo, "_repair_generation_job_references_to_result", fail_repair)
    with pytest.raises(GenerationJobConflict, match="repair unavailable"):
        repo.discard_job(source.id)

    monkeypatch.setattr(GenerationJobRepository, "_repair_generation_job_references_to_result", original_repair)
    recover_interrupted_generation_jobs(library)

    resumed = GenerationJobRepository(library).get_job(source.id)
    repaired = GenerationJobRepository(library).get_job(downstream.id)
    assert resumed.metadata.get("discard_repair_pending") is None
    assert repaired.parameters["input_images"][0]["result_path"].startswith(
        f"generation-references/{downstream.id}/"
    )
    assert not (library / source.result_path).exists()


def test_generation_job_can_discard_unsaved_result_and_retry_same_settings(tmp_path, monkeypatch):
    c = client(tmp_path)
    source_item = create_source_item(c)
    enqueue_calls = []

    def fake_enqueue(library_path, *, provider):
        enqueue_calls.append((Path(library_path), provider))

    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", fake_enqueue)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_language": "en",
        "prompt_text": "A cinematic moonlit robot",
        "edited_prompt_text": "A cinematic moonlit robot holding a lantern",
        "reference_image_ids": ["img_reference"],
        "parameters": {"requested_aspect_ratio": "1:1", "quality": "high"},
    }).json()
    c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("blue"), "image/png")},
    )
    staged = c.get(f"/api/generation-jobs/{job['id']}").json()
    result_path = staged["result_path"]
    result_file = tmp_path / "library" / result_path
    assert result_file.is_file()
    enqueue_calls.clear()

    response = c.post(f"/api/generation-jobs/{job['id']}/discard-and-retry")

    assert response.status_code == 200
    payload = response.json()
    discarded = payload["discarded_job"]
    retry = payload["retry_job"]
    assert discarded["id"] == job["id"]
    assert discarded["status"] == "discarded"
    assert discarded["result_path"] is None
    assert discarded["result_width"] is None
    assert discarded["result_height"] is None
    assert discarded["result_sha256"] is None
    assert discarded["metadata"]["discarded_result_path"] == result_path
    assert discarded["metadata"]["retried_by_generation_job_id"] == retry["id"]
    assert not result_file.exists()
    assert retry["id"] != job["id"]
    assert retry["status"] == "queued"
    assert retry["source_item_id"] == source_item["id"]
    assert retry["provider"] == "openai_codex_oauth_native"
    assert retry["model"] == "gpt-image-2"
    assert retry["prompt_text"] == "A cinematic moonlit robot"
    assert retry["edited_prompt_text"] == "A cinematic moonlit robot holding a lantern"
    assert retry["reference_image_ids"] == ["img_reference"]
    assert retry["parameters"] == {"requested_aspect_ratio": "1:1", "quality": "high"}
    assert retry["metadata"]["retry_of_generation_job_id"] == job["id"]
    assert retry["metadata"]["retry_reason"] == "discard_and_retry"
    assert enqueue_calls == [(tmp_path / "library", "openai_codex_oauth_native")]


def test_failed_generation_job_can_be_retried_without_rerunning_original(tmp_path, monkeypatch):
    c = client(tmp_path)
    source_item = create_source_item(c)
    enqueue_calls = []

    def fake_enqueue(library_path, *, provider):
        enqueue_calls.append((Path(library_path), provider))

    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", fake_enqueue)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "mode": "text_to_image",
        "provider": "openai_codex_oauth_native",
        "model": "gpt-image-2",
        "prompt_language": "en",
        "prompt_text": "A failed robot portrait",
        "edited_prompt_text": "A failed robot portrait in rain",
        "reference_image_ids": ["img_reference"],
        "parameters": {"requested_aspect_ratio": "1:1", "quality": "high"},
    }).json()
    repo = GenerationJobRepository(tmp_path / "library")
    repo.mark_failed(job["id"], "Generation job was interrupted by backend restart. Retry to run it again.")
    enqueue_calls.clear()

    response = c.post(f"/api/generation-jobs/{job['id']}/retry")

    assert response.status_code == 200
    retry = response.json()
    original = c.get(f"/api/generation-jobs/{job['id']}").json()
    assert original["status"] == "failed"
    assert original["metadata"]["retried_by_generation_job_id"] == retry["id"]
    assert retry["id"] != job["id"]
    assert retry["status"] == "queued"
    assert retry["source_item_id"] == source_item["id"]
    assert retry["provider"] == "openai_codex_oauth_native"
    assert retry["model"] == "gpt-image-2"
    assert retry["prompt_text"] == "A failed robot portrait"
    assert retry["edited_prompt_text"] == "A failed robot portrait in rain"
    assert retry["reference_image_ids"] == ["img_reference"]
    assert retry["parameters"] == {"requested_aspect_ratio": "1:1", "quality": "high"}
    assert retry["metadata"]["retry_of_generation_job_id"] == job["id"]
    assert retry["metadata"]["retry_reason"] == "failed_retry"
    assert enqueue_calls == [(tmp_path / "library", "openai_codex_oauth_native")]

    second_retry = c.post(f"/api/generation-jobs/{job['id']}/retry")
    assert second_retry.status_code == 409
    assert "already been retried" in second_retry.json()["detail"]
    jobs = c.get("/api/generation-jobs", params={"limit": 10}).json()["jobs"]
    assert [candidate["metadata"].get("retry_of_generation_job_id") for candidate in jobs].count(job["id"]) == 1


def _concurrent_results(callable_, count=2):
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(callable_) for _ in range(count)]
        return [future.result() for future in futures]


def test_concurrent_accept_result_creates_one_image_and_one_winner(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(source_item_id=source_item["id"], provider="manual_upload", prompt_text="concurrent accept"))
    repo.stage_result(job.id, png_bytes("blue"), "generated.png")

    def accept():
        try:
            return ("ok", repo.accept_result(job.id))
        except GenerationJobConflict as exc:
            return ("conflict", str(exc))

    results = _concurrent_results(accept)

    assert [result[0] for result in results].count("ok") == 1
    assert [result[0] for result in results].count("conflict") == 1
    assert repo.get_job(job.id).status == "accepted"
    assert len(repo.items.get_item(source_item["id"]).images) == 1


def test_concurrent_accept_as_new_item_creates_one_item_and_one_winner(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(source_item_id=source_item["id"], provider="manual_upload", prompt_text="concurrent variant"))
    repo.stage_result(job.id, png_bytes("purple"), "generated.png")

    def accept_as_new():
        try:
            return ("ok", repo.accept_result_as_new_item(job.id))
        except GenerationJobConflict as exc:
            return ("conflict", str(exc))

    results = _concurrent_results(accept_as_new)

    assert [result[0] for result in results].count("ok") == 1
    assert [result[0] for result in results].count("conflict") == 1
    assert repo.get_job(job.id).status == "accepted"
    assert repo.items.list_items(limit=10).total == 2


def test_stale_accept_claim_only_recovers_the_same_acceptance_mode(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(
        GenerationJobCreate(
            source_item_id=source_item["id"],
            provider="manual_upload",
            prompt_text="mode-safe recovery",
        )
    )
    repo.stage_result(job.id, png_bytes("purple"), "generated.png")
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (
                json.dumps({
                    "_generation_accept_claim": {
                        "token": "accept_crashed_process",
                        "mode": "existing_item",
                    },
                    "_generation_accept_claim_at": stale_at,
                }),
                stale_at,
                job.id,
            ),
        )
        conn.commit()

    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.accept_result_as_new_item(job.id)

    accepted = repo.accept_result(job.id)
    assert accepted.job.status == "accepted"
    assert repo.items.list_items(limit=10).total == 1
    assert len(repo.items.get_item(source_item["id"]).images) == 1


def test_stage_result_cannot_replace_result_during_acceptance(tmp_path, monkeypatch):
    source = GenerationJobRepository(tmp_path / "library").items.create_item(
        ItemCreate(title="Stage race source", prompts=[PromptIn(language="en", text="source", is_original=True)])
    )
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(
        GenerationJobCreate(
            source_item_id=source.id,
            provider="manual_upload",
            prompt_text="stage accept race",
        )
    )
    staged = repo.stage_result(job.id, png_bytes("blue"), "first.png")
    store_started = Event()
    release_store = Event()
    original_store = repo._store_prepared_image

    def gated_store(prepared):
        store_started.set()
        assert release_store.wait(5)
        return original_store(prepared)

    monkeypatch.setattr(repo, "_store_prepared_image", gated_store)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(repo.accept_result, job.id)
        assert store_started.wait(5)
        with pytest.raises(GenerationJobConflict, match="currently being accepted"):
            repo.stage_result(job.id, png_bytes("red"), "second.png")
        release_store.set()
        accepted = pending.result()

    final_job = repo.get_job(job.id)
    accepted_image = repo.items.get_image(accepted.job.accepted_image_id)
    with Image.open(repo.library_path / accepted_image.original_path) as image:
        assert image.getpixel((0, 0)) == (0, 0, 255)
    assert final_job.status == "accepted"
    assert final_job.result_path == staged.result_path
    assert final_job.result_sha256 == staged.result_sha256
    result_directory = repo.library_path / "generation-results" / job.id
    assert not any(
        path.name.startswith("result-") and path != repo.library_path / staged.result_path
        for path in result_directory.iterdir()
    )


def test_stage_result_rejects_truncated_image_before_marking_job_succeeded(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="truncated result"))
    truncated = png_bytes("blue")[:-12]

    with pytest.raises(GenerationJobConflict, match="invalid"):
        repo.stage_result(job.id, truncated, "truncated.png")

    current = repo.get_job(job.id)
    assert current.status == "queued"
    assert current.result_path is None
    result_directory = repo.library_path / "generation-results" / job.id
    assert not result_directory.exists()


def test_accept_and_discard_race_does_not_resurrect_discarded_job(tmp_path, monkeypatch):
    c = client(tmp_path)
    source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(source_item_id=source_item["id"], provider="manual_upload", prompt_text="accept discard race"))
    repo.stage_result(job.id, png_bytes("green"), "generated.png")
    claim_started = Event()
    release_claim = Event()
    claim = repo._claim_acceptance

    def delayed_claim(*args, **kwargs):
        claim_started.set()
        assert release_claim.wait(5)
        return claim(*args, **kwargs)

    monkeypatch.setattr(repo, "_claim_acceptance", delayed_claim)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(repo.accept_result, job.id)
        assert claim_started.wait(5)
        discarded = repo.discard_job(job.id)
        release_claim.set()
        with pytest.raises(GenerationJobConflict):
            pending.result()

    assert discarded.status == "discarded"
    assert repo.get_job(job.id).status == "discarded"
    assert repo.items.get_item(source_item["id"]).images == []


def test_accept_side_effect_failure_releases_claim_and_compensates_image(tmp_path, monkeypatch):
    c = client(tmp_path)
    source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(source_item_id=source_item["id"], provider="manual_upload", prompt_text="accept cleanup"))
    staged = repo.stage_result(job.id, png_bytes("orange"), "generated.png")
    result_path = tmp_path / "library" / staged.result_path

    def fail_reference_storage(*_args, **_kwargs):
        raise RuntimeError("reference side effect failed")

    monkeypatch.setattr(repo, "_store_input_reference_images", fail_reference_storage)
    with pytest.raises(RuntimeError, match="reference side effect failed"):
        repo.accept_result(job.id)

    assert repo.get_job(job.id).status == "succeeded"
    assert repo.get_job(job.id).metadata.get("_generation_accept_claim") is None
    assert repo.items.get_item(source_item["id"]).images == []
    assert result_path.is_file()


def test_stale_legacy_accept_claim_is_recovered_for_accept(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(source_item_id=source_item["id"], provider="manual_upload", prompt_text="recover stale claim"))
    repo.stage_result(job.id, png_bytes("yellow"), "generated.png")
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps({"_generation_accept_claim": "accept_crashed_process"}), stale_at, job.id),
        )
        conn.commit()

    accepted = repo.accept_result(job.id)

    assert accepted.job.status == "accepted"
    assert accepted.job.metadata.get("_generation_accept_claim") is None


def test_accept_reuses_side_effects_after_crash_before_finalize_and_legacy_claim_recovery(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.items.create_item(ItemCreate(title="Crash source", prompts=[PromptIn(language="en", text="source", is_original=True)]))
    job = repo.create_job(GenerationJobCreate(source_item_id=source.id, provider="manual_upload", prompt_text="crash accept"))
    repo.stage_result(job.id, png_bytes("navy"), "generated.png")

    class SimulatedCrash(BaseException):
        pass

    finalize = repo._finalize_acceptance
    monkeypatch.setattr(repo, "_finalize_acceptance", lambda *_args, **_kwargs: (_ for _ in ()).throw(SimulatedCrash()))
    with pytest.raises(SimulatedCrash):
        repo.accept_result(job.id)

    crashed = repo.get_job(job.id)
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    legacy_metadata = dict(crashed.metadata)
    legacy_metadata.pop("_generation_accept_artifacts", None)
    legacy_metadata.pop("_generation_accept_claim_at", None)
    legacy_metadata["_generation_accept_claim"] = "legacy-crashed-claim"
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps(legacy_metadata), stale_at, job.id),
        )
        conn.commit()

    monkeypatch.setattr(repo, "_finalize_acceptance", finalize)
    accepted = repo.accept_result(job.id)

    assert accepted.job.status == "accepted"
    assert len(repo.items.get_item(source.id).images) == 1
    assert accepted.job.accepted_image_id == repo.items.get_item(source.id).images[0].id
    assert not any(key.startswith("_generation_accept_") for key in accepted.job.metadata)


def test_accept_lease_loss_during_store_cleans_losing_claim_side_effects(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.items.create_item(ItemCreate(title="Lease source", prompts=[PromptIn(language="en", text="source", is_original=True)]))
    job = repo.create_job(GenerationJobCreate(source_item_id=source.id, provider="manual_upload", prompt_text="lease race"))
    repo.stage_result(job.id, png_bytes("maroon"), "generated.png")
    monkeypatch.setattr("backend.services.generation_jobs.ACCEPT_CLAIM_LEASE_AFTER", timedelta(0))
    started = Event()
    release = Event()
    original_store = repo._store_prepared_image

    def gated_store(prepared):
        started.set()
        assert release.wait(5)
        return original_store(prepared)

    monkeypatch.setattr(repo, "_store_prepared_image", gated_store)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(repo.accept_result, job.id)
        assert started.wait(5)
        discarded = repo.discard_job(job.id)
        release.set()
        with pytest.raises(GenerationJobConflict):
            pending.result()

    assert discarded.status == "discarded"
    assert repo.items.get_item(source.id).images == []
    originals = tmp_path / "library" / "originals"
    assert not originals.exists() or not any(path.is_file() for path in originals.rglob("*"))


def test_accept_as_new_reuses_item_and_image_after_crash_before_finalize(tmp_path, monkeypatch):
    repo = GenerationJobRepository(tmp_path / "library")
    source = repo.items.create_item(ItemCreate(title="Crash source", prompts=[PromptIn(language="en", text="source", is_original=True)]))
    job = repo.create_job(GenerationJobCreate(source_item_id=source.id, provider="manual_upload", prompt_text="crash variant"))
    repo.stage_result(job.id, png_bytes("indigo"), "generated.png")

    class SimulatedCrash(BaseException):
        pass

    finalize = repo._finalize_acceptance
    monkeypatch.setattr(repo, "_finalize_acceptance", lambda *_args, **_kwargs: (_ for _ in ()).throw(SimulatedCrash()))
    with pytest.raises(SimulatedCrash):
        repo.accept_result_as_new_item(job.id)

    crashed = repo.get_job(job.id)
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    legacy_metadata = dict(crashed.metadata)
    legacy_metadata.pop("_generation_accept_artifacts", None)
    legacy_metadata.pop("_generation_accept_claim_at", None)
    legacy_metadata["_generation_accept_claim"] = "legacy-crashed-claim"
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps(legacy_metadata), stale_at, job.id),
        )
        conn.commit()

    monkeypatch.setattr(repo, "_finalize_acceptance", finalize)
    accepted = repo.accept_result_as_new_item(job.id)

    assert accepted.job.status == "accepted"
    assert accepted.item.id != source.id
    assert repo.items.list_items(limit=10).total == 2
    assert len(accepted.item.images) == 1
    assert not any(key.startswith("_generation_accept_") for key in accepted.job.metadata)


def test_stale_timestamped_accept_claim_is_recovered_for_discard_and_retry(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="recover stale discard"))
    repo.stage_result(job.id, png_bytes("teal"), "generated.png")
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps({
                "_generation_accept_claim": "accept_crashed_process",
                "_generation_accept_claim_at": stale_at,
            }), stale_at, job.id),
        )
        conn.commit()

    retried = repo.discard_and_retry_job(job.id)

    assert retried.discarded_job.status == "discarded"
    assert retried.retry_job.status == "queued"


def test_stale_timestamped_accept_claim_is_recovered_for_discard(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="recover stale discard only"))
    repo.stage_result(job.id, png_bytes("gray"), "generated.png")
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps({
                "_generation_accept_claim": "accept_crashed_process",
                "_generation_accept_claim_at": stale_at,
            }), stale_at, job.id),
        )
        conn.commit()

    discarded = repo.discard_job(job.id)

    assert discarded.status == "discarded"


def test_stale_acceptance_artifacts_must_resume_before_discard(tmp_path, monkeypatch):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    source = repo.items.create_item(
        ItemCreate(title="Interrupted save source", prompts=[PromptIn(language="en", text="source", is_original=True)])
    )
    job = repo.create_job(
        GenerationJobCreate(source_item_id=source.id, provider="manual_upload", prompt_text="interrupted save")
    )
    repo.stage_result(job.id, png_bytes("purple"), "generated.png")

    class SimulatedCrash(BaseException):
        pass

    finalize = repo._finalize_acceptance

    def crash_before_finalize(*_args, **_kwargs):
        raise SimulatedCrash()

    monkeypatch.setattr(repo, "_finalize_acceptance", crash_before_finalize)
    with pytest.raises(SimulatedCrash):
        repo.accept_result(job.id)

    crashed = repo.get_job(job.id)
    assert crashed.metadata.get("_generation_accept_artifacts")
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    stale_metadata = dict(crashed.metadata)
    stale_metadata["_generation_accept_claim_at"] = stale_at
    with connect(library) as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps(stale_metadata), stale_at, job.id),
        )
        conn.commit()

    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.discard_job(job.id)
    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.discard_and_retry_job(job.id)

    monkeypatch.setattr(repo, "_finalize_acceptance", finalize)
    accepted = repo.accept_result(job.id)
    assert accepted.job.status == "accepted"
    assert len(repo.items.get_item(source.id).images) == 1


def test_stale_new_item_without_artifact_marker_must_resume_before_discard(tmp_path, monkeypatch):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    source = repo.items.create_item(
        ItemCreate(title="Interrupted variant source", prompts=[PromptIn(language="en", text="source", is_original=True)])
    )
    job = repo.create_job(
        GenerationJobCreate(source_item_id=source.id, provider="manual_upload", prompt_text="interrupted variant")
    )
    repo.stage_result(job.id, png_bytes("plum"), "generated.png")

    class SimulatedCrash(BaseException):
        pass

    record_artifacts = repo._record_acceptance_artifacts
    monkeypatch.setattr(
        repo,
        "_record_acceptance_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SimulatedCrash()),
    )
    with pytest.raises(SimulatedCrash):
        repo.accept_result_as_new_item(job.id)

    crashed = repo.get_job(job.id)
    assert crashed.metadata.get("_generation_accept_artifacts") is None
    assert repo.items.list_items(limit=10).total == 2
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    stale_metadata = dict(crashed.metadata)
    stale_metadata["_generation_accept_claim_at"] = stale_at
    with connect(library) as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps(stale_metadata), stale_at, job.id),
        )
        conn.commit()

    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.discard_job(job.id)
    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.discard_and_retry_job(job.id)

    monkeypatch.setattr(repo, "_record_acceptance_artifacts", record_artifacts)
    accepted = repo.accept_result_as_new_item(job.id)
    assert accepted.job.status == "accepted"
    assert repo.items.list_items(limit=10).total == 2
    assert accepted.item.id != source.id


def test_stale_existing_item_without_artifact_marker_must_resume_before_discard(tmp_path, monkeypatch):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    source = repo.items.create_item(
        ItemCreate(title="Interrupted attach source", prompts=[PromptIn(language="en", text="source", is_original=True)])
    )
    job = repo.create_job(
        GenerationJobCreate(source_item_id=source.id, provider="manual_upload", prompt_text="interrupted attach")
    )
    repo.stage_result(job.id, png_bytes("orchid"), "generated.png")

    class SimulatedCrash(BaseException):
        pass

    record_artifacts = repo._record_acceptance_artifacts
    monkeypatch.setattr(
        repo,
        "_record_acceptance_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SimulatedCrash()),
    )
    with pytest.raises(SimulatedCrash):
        repo.accept_result(job.id)

    crashed = repo.get_job(job.id)
    assert crashed.metadata.get("_generation_accept_artifacts") is None
    assert len(repo.items.get_item(source.id).images) == 1
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    stale_metadata = dict(crashed.metadata)
    stale_metadata["_generation_accept_claim_at"] = stale_at
    with connect(library) as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
            (json.dumps(stale_metadata), stale_at, job.id),
        )
        conn.commit()

    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.discard_job(job.id)
    with pytest.raises(GenerationJobConflict, match="interrupted save"):
        repo.discard_and_retry_job(job.id)

    monkeypatch.setattr(repo, "_record_acceptance_artifacts", record_artifacts)
    accepted = repo.accept_result(job.id)
    assert accepted.job.status == "accepted"
    assert len(repo.items.get_item(source.id).images) == 1


def test_fresh_accept_claim_blocks_accept_discard_and_retry(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="fresh claim"))
    repo.stage_result(job.id, png_bytes("pink"), "generated.png")
    _, claim_token = repo._claim_acceptance(job.id, require_source_item=False)

    with pytest.raises(GenerationJobConflict, match="already being accepted"):
        repo._claim_acceptance(job.id, require_source_item=False)
    with pytest.raises(GenerationJobConflict):
        repo.discard_job(job.id)
    with pytest.raises(GenerationJobConflict):
        repo.discard_and_retry_job(job.id)

    repo._release_acceptance(job.id, claim_token)


def test_stage_result_merges_provider_metadata_without_dropping_retry_provenance(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    original = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="retry metadata"))
    repo.mark_failed(original.id, "temporary failure")
    retry = repo.retry_failed_job(original.id)

    staged = repo.stage_result(retry.id, png_bytes("white"), "generated.png", {
        "provider_request_id": "req_123",
        "_generation_accept_claim": "forged-claim",
        "_generation_accept_artifacts": {"item_id": "forged-item"},
        "reference_image_copies": [{"copied_path": "forged-copy"}],
    })
    reloaded = repo.get_job(retry.id)

    assert staged.metadata["retry_of_generation_job_id"] == original.id
    assert staged.metadata["provider_request_id"] == "req_123"
    assert reloaded.metadata["retry_of_generation_job_id"] == original.id
    assert reloaded.metadata.get("_generation_accept_claim") is None
    assert reloaded.metadata.get("_generation_accept_artifacts") is None
    assert reloaded.metadata.get("reference_image_copies") is None


def test_stage_result_sanitizes_provider_metadata_before_storage_and_api_output(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={"prompt_text": "metadata boundary"}).json()
    response = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("white"), "image/png")},
        data={
            "metadata": json.dumps({
                "provider_request_id": "req_safe",
                "auth_mode": "codex_oauth_native",
                "tokenValue": "token-secret",
                "APIKey": "api-key-secret",
                "nested": {
                    "headers": {"Authorization": "Bearer secret"},
                    "data_url": "data:image/png;base64,private-metadata-image",
                    "safe": "kept",
                },
            }),
        },
    )

    assert response.status_code == 200
    expected = {
        "provider_request_id": "req_safe",
        "auth_mode": "codex_oauth_native",
        "nested": {"safe": "kept"},
    }
    assert response.json()["metadata"] == expected
    assert GenerationJobRepository(tmp_path / "library").get_job(job["id"]).metadata == expected


def test_generation_result_and_failure_updates_do_not_overwrite_terminal_outcomes(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    succeeded = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="success wins"))
    repo.stage_result(succeeded.id, png_bytes("white"), "generated.png")

    with pytest.raises(GenerationJobConflict, match="cannot be marked failed"):
        repo.mark_failed(succeeded.id, "late provider failure")
    assert repo.get_job(succeeded.id).status == "succeeded"

    failed = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="failure wins"))
    repo.mark_failed(failed.id, "provider failed")
    with pytest.raises(GenerationJobConflict, match="cannot be staged"):
        repo.stage_result(failed.id, png_bytes("black"), "late-result.png")
    assert repo.get_job(failed.id).status == "failed"


def test_concurrent_failed_retry_creates_one_replacement_and_preserves_batch_fields(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    generation_set = repo.create_job_set(GenerationJobCreate(provider="openai_codex_oauth_native", prompt_text="batch failed retry"), 3)
    job = generation_set.jobs[1]
    repo.mark_failed(job.id, "failed")

    def retry():
        try:
            return ("ok", repo.retry_failed_job(job.id))
        except GenerationJobConflict as exc:
            return ("conflict", str(exc))

    results = _concurrent_results(retry)

    assert [result[0] for result in results].count("ok") == 1
    assert [result[0] for result in results].count("conflict") == 1
    retry_job = next(result[1] for result in results if result[0] == "ok")
    assert retry_job.generation_group_id == job.generation_group_id
    assert retry_job.generation_group_index == job.generation_group_index
    assert retry_job.generation_group_size == job.generation_group_size
    with connect(tmp_path / "library") as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM generation_jobs WHERE metadata LIKE ?",
            (f'%"retry_of_generation_job_id": "{job.id}"%',),
        ).fetchone()[0] == 1


def test_concurrent_discard_retry_creates_one_replacement_and_preserves_batch_fields(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    generation_set = repo.create_job_set(GenerationJobCreate(provider="openai_codex_oauth_native", prompt_text="batch discard retry"), 3)
    job = generation_set.jobs[1]
    staged = repo.stage_result(job.id, png_bytes("red"), "generated.png")

    def retry():
        try:
            return ("ok", repo.discard_and_retry_job(job.id))
        except GenerationJobConflict as exc:
            return ("conflict", str(exc))

    results = _concurrent_results(retry)

    assert [result[0] for result in results].count("ok") == 1
    assert [result[0] for result in results].count("conflict") == 1
    retry_job = next(result[1].retry_job for result in results if result[0] == "ok")
    assert retry_job.generation_group_id == job.generation_group_id
    assert retry_job.generation_group_index == job.generation_group_index
    assert retry_job.generation_group_size == job.generation_group_size
    assert not (tmp_path / "library" / staged.result_path).exists()


def test_running_generation_job_is_not_stale_before_ten_minutes(tmp_path):
    repo, job_id = _make_running_job(tmp_path, started_minutes_ago=9)

    try:
        repo.mark_stale_running_failed(job_id)
    except GenerationJobConflict as exc:
        assert "not stale yet" in str(exc)
    else:
        raise AssertionError("Expected job to remain running before ten minutes")


def test_stale_running_generation_job_fails_with_retryable_message(tmp_path):
    repo, job_id = _make_running_job(tmp_path, started_minutes_ago=11)
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=? WHERE id=?",
            (json.dumps({"note": "access_token=stale-canary", "safe": "kept"}), job_id),
        )
        conn.commit()

    failed = repo.mark_stale_running_failed(job_id)
    retry = repo.retry_failed_job(job_id)

    assert failed.status == "failed"
    assert failed.error == "Generation took too long and may have stalled. Retry to run it again."
    assert failed.metadata["stale_running_marked_failed"] is True
    assert failed.metadata["stale_running_threshold_minutes"] == 10
    assert failed.metadata["note"] == "[redacted credential data]"
    assert failed.metadata["safe"] == "kept"
    assert "stale-canary" not in json.dumps(failed.metadata)
    assert retry.status == "queued"
    assert retry.metadata["retry_of_generation_job_id"] == job_id


def test_discard_sanitizes_legacy_metadata_before_rewriting_job(tmp_path):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="discard boundary"))
    repo.stage_result(job.id, png_bytes("blue"), "generated.png")
    with connect(library) as conn:
        conn.execute(
            "UPDATE generation_jobs SET metadata=? WHERE id=?",
            (json.dumps({"note": "access_token=discard-canary", "safe": "kept"}), job.id),
        )
        conn.commit()

    discarded = repo.discard_job(job.id)

    assert discarded.metadata["note"] == "[redacted credential data]"
    assert discarded.metadata["safe"] == "kept"
    assert "discard-canary" not in json.dumps(discarded.metadata)


def test_queued_and_running_generation_jobs_can_be_cancelled(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    queued = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued"))
    running = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="running"))
    repo.mark_running(running.id)

    assert repo.cancel_job(queued.id).status == "cancelled"
    assert repo.cancel_job(running.id).status == "cancelled"


def test_bulk_cancel_cancels_more_than_default_list_page(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    jobs = [repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text=f"queued {index}")) for index in range(1005)]

    assert repo.cancel_active_jobs() == 1005
    assert all(repo.get_job(job.id).status == "cancelled" for job in jobs)


def test_recover_interrupted_generation_jobs_marks_only_provider_running_failed(tmp_path):
    from backend.services.generation_queue import INTERRUPTED_BY_BACKEND_RESTART_ERROR, recover_interrupted_generation_jobs
    from backend.services.openai_codex_native import PROVIDER_ID

    repo = GenerationJobRepository(tmp_path / "library")
    running_provider = repo.create_job(GenerationJobCreate(provider=PROVIDER_ID, prompt_text="provider running"))
    queued_provider = repo.create_job(GenerationJobCreate(provider=PROVIDER_ID, prompt_text="provider queued"))
    running_manual = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="manual running"))
    repo.mark_running(running_provider.id)
    repo.mark_running(running_manual.id)

    recovered = recover_interrupted_generation_jobs(tmp_path / "library")

    assert [job.id for job in recovered] == [running_provider.id]
    assert repo.get_job(running_provider.id).status == "failed"
    assert repo.get_job(running_provider.id).error == INTERRUPTED_BY_BACKEND_RESTART_ERROR
    assert repo.get_job(queued_provider.id).status == "queued"
    assert repo.get_job(running_manual.id).status == "running"


def test_generation_job_retry_rejects_saved_or_unfinished_jobs(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    queued = c.post("/api/generation-jobs", json={"source_item_id": source_item["id"], "prompt_text": "queued"}).json()
    assert c.post(f"/api/generation-jobs/{queued['id']}/discard-and-retry").status_code == 409

    saved = c.post("/api/generation-jobs", json={"source_item_id": source_item["id"], "prompt_text": "saved"}).json()
    c.post(f"/api/generation-jobs/{saved['id']}/result", files={"file": ("generated.png", png_bytes("blue"), "image/png")})
    c.post(f"/api/generation-jobs/{saved['id']}/accept")

    response = c.post(f"/api/generation-jobs/{saved['id']}/discard-and-retry")

    assert response.status_code == 409
    assert "Saved generation jobs cannot be retried" in response.json()["detail"]


def test_generation_job_rejects_accept_without_result(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    job = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "prompt_text": "A cinematic moonlit robot",
    }).json()

    response = c.post(f"/api/generation-jobs/{job['id']}/accept")

    assert response.status_code == 409
    assert "succeeded" in response.json()["detail"]


def test_generation_job_tables_are_migrated(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/health").status_code == 200
    with connect(tmp_path / "library") as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(generation_jobs)")}
    assert "generation_jobs" in tables
    assert "cancelled_at" in columns


def test_generation_job_can_be_cancelled_before_result(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={"prompt_text": "cancel me"}).json()

    cancelled = c.post(f"/api/generation-jobs/{job['id']}/cancel")

    assert cancelled.status_code == 200
    payload = cancelled.json()
    assert payload["status"] == "cancelled"
    assert payload["cancelled_at"]
    assert payload["completed_at"]
    assert c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("red"), "image/png")},
    ).status_code == 409
    assert c.post(f"/api/generation-jobs/{job['id']}/cancel").status_code == 409


def test_native_generation_job_create_enqueues_background_runner(tmp_path, monkeypatch):
    c = client(tmp_path)
    calls = []

    def fake_enqueue(library_path, *, provider):
        calls.append((Path(library_path), provider))

    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", fake_enqueue)

    created = c.post("/api/generation-jobs", json={
        "provider": "openai_codex_oauth_native",
        "prompt_text": "start immediately",
    })

    assert created.status_code == 200
    assert calls == [(tmp_path / "library", "openai_codex_oauth_native")]


def test_app_startup_marks_interrupted_running_jobs_failed_and_drains_queued(tmp_path, monkeypatch):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    running = repo.create_job(GenerationJobCreate(
        provider="openai_codex_oauth_native",
        prompt_text="in-flight before restart",
    ))
    queued = repo.create_job(GenerationJobCreate(
        provider="openai_codex_oauth_native",
        prompt_text="queued before restart",
    ))
    manual_queued = repo.create_job(GenerationJobCreate(
        provider="manual_upload",
        prompt_text="manual upload should remain untouched",
    ))
    repo.mark_running(running.id)
    enqueue_calls = []

    def fake_enqueue(library_path, *, provider):
        enqueue_calls.append((Path(library_path), provider))

    monkeypatch.setattr("backend.main.enqueue_generation_jobs", fake_enqueue)

    with TestClient(create_app(library_path=library)) as c:
        assert c.get("/api/health").status_code == 200

    recovered_running = repo.get_job(running.id)
    recovered_queued = repo.get_job(queued.id)
    untouched_manual = repo.get_job(manual_queued.id)
    assert recovered_running.status == "failed"
    assert recovered_running.completed_at
    assert "interrupted by backend restart" in recovered_running.error
    assert "Retry" in recovered_running.error
    assert recovered_queued.status == "queued"
    assert untouched_manual.status == "queued"
    assert enqueue_calls == [(library, "openai_codex_oauth_native")]


def test_generation_queue_runs_at_most_five_native_jobs(tmp_path, monkeypatch):
    from backend.services import generation_queue

    deadline = time.time() + 3
    while generation_queue._active and time.time() < deadline:
        time.sleep(0.02)
    assert not generation_queue._active

    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job_ids = [repo.create_job(GenerationJobCreate(
        provider="openai_codex_oauth_native",
        prompt_text=f"queued job {index}",
    )).id for index in range(6)]
    submitted = []
    isolated_active: set[str] = set()
    monkeypatch.setattr(generation_queue, "_active", isolated_active)
    monkeypatch.setattr(
        generation_queue._executor,
        "submit",
        lambda fn, *args: submitted.append((fn, args)),
    )

    generation_queue.enqueue_generation_jobs(library)

    assert len(submitted) == generation_queue.MAX_CONCURRENT_GENERATION_JOBS
    submitted_ids = {args[1] for _fn, args in submitted}
    assert len(submitted_ids) == generation_queue.MAX_CONCURRENT_GENERATION_JOBS
    assert submitted_ids < set(job_ids)
    assert isolated_active == submitted_ids
    assert [repo.get_job(job_id).status for job_id in job_ids] == ["queued"] * 6


@pytest.mark.parametrize("count", (1, 3, 5, 10))
def test_generation_job_set_accepts_supported_counts(tmp_path, count):
    c = client(tmp_path)
    response = c.post("/api/generation-jobs/sets", json={
        "job": {"provider": "test_provider", "prompt_text": "variant"},
        "count": count,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == count
    assert [job["generation_group_index"] for job in payload["jobs"]] == list(range(1, count + 1))
    assert {job["generation_group_size"] for job in payload["jobs"]} == {count}


def test_generation_job_set_rejects_unsupported_count(tmp_path):
    c = client(tmp_path)
    response = c.post("/api/generation-jobs/sets", json={
        "job": {"provider": "manual_upload", "prompt_text": "variant"},
        "count": 2,
    })
    assert response.status_code == 422


def test_generation_job_set_keeps_manual_upload_single(tmp_path):
    c = client(tmp_path)
    response = c.post("/api/generation-jobs/sets", json={
        "job": {"provider": "manual_upload", "prompt_text": "manual result"},
        "count": 3,
    })
    assert response.status_code == 409
    assert response.json()["detail"] == "Manual result upload supports one image at a time"
    assert c.get("/api/generation-jobs").json()["total"] == 0


def test_generation_job_set_create_and_cancel_retry_after_queue_database_lock(tmp_path, monkeypatch):
    import sqlite3
    from backend.services import generation_queue

    scheduled = []
    monkeypatch.setattr(
        generation_queue,
        "enqueue_generation_jobs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")),
    )
    monkeypatch.setattr(
        generation_queue,
        "_schedule_pause_wake",
        lambda library_path, provider, delay: scheduled.append((library_path, provider, delay)),
    )
    c = client(tmp_path)

    created = c.post("/api/generation-jobs/sets", json={
        "job": {"provider": "openai_codex_oauth_native", "prompt_text": "locked set"},
        "count": 3,
    })
    assert created.status_code == 200
    payload = created.json()
    assert payload["total"] == 3
    assert c.get("/api/generation-jobs").json()["total"] == 3

    cancelled = c.post(f"/api/generation-jobs/sets/{payload['generation_group_id']}/cancel-remaining")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] == 3
    assert scheduled == [
        (tmp_path / "library", "openai_codex_oauth_native", generation_queue.QUEUE_RESUME_RETRY_SECONDS),
        (tmp_path / "library", "openai_codex_oauth_native", generation_queue.QUEUE_RESUME_RETRY_SECONDS),
    ]


def test_generation_job_set_rolls_back_rows_and_reference_clones(tmp_path, monkeypatch):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    calls = 0

    def prepare(job_id, parameters):
        nonlocal calls
        calls += 1
        job_root = library / "generation-references" / job_id
        job_root.mkdir(parents=True, exist_ok=True)
        (job_root / "clone.png").write_bytes(png_bytes())
        if calls == 2:
            raise GenerationJobConflict("clone failed")
        return dict(parameters), []

    monkeypatch.setattr(repo, "_prepare_reference_input_clones", prepare)
    with pytest.raises(GenerationJobConflict, match="clone failed"):
        repo.create_job_set(GenerationJobCreate(provider="test_provider", prompt_text="variant"), 3)
    with connect(library) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_jobs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM generation_sets").fetchone()[0] == 0
    assert not (library / "generation-references").exists() or not list((library / "generation-references").iterdir())


def test_generation_job_set_progress_and_cancel_preserve_terminal_results(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    created = repo.create_job_set(GenerationJobCreate(provider="test_provider", prompt_text="variant"), 3)
    repo.mark_running(created.jobs[0].id)
    repo.mark_failed(created.jobs[0].id, "safe failure")
    repo.stage_result(created.jobs[1].id, png_bytes(), "result.png")
    progress = repo.get_generation_set(created.generation_group_id)
    assert (progress.failed, progress.succeeded, progress.queued, progress.completed, progress.remaining) == (1, 1, 1, 2, 1)
    cancelled = repo.cancel_generation_set(created.generation_group_id)
    assert (cancelled.failed, cancelled.succeeded, cancelled.cancelled, cancelled.completed, cancelled.remaining) == (1, 1, 1, 3, 0)


def test_provider_rate_limit_backoff_is_durable_and_simultaneous_incidents_do_not_multiply(tmp_path):
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    first = repo.record_provider_rate_limit("openai_codex_oauth_native")
    second = repo.record_provider_rate_limit("openai_codex_oauth_native")
    assert first.backoff_seconds == 60
    assert second.backoff_seconds == 60
    extended = repo.record_provider_rate_limit("openai_codex_oauth_native", 300)
    assert extended.retry_after_seconds >= 299
    assert extended.backoff_seconds == 300
    with connect(library) as conn:
        assert conn.execute(
            "SELECT incident_count FROM provider_queue_states WHERE provider=?",
            ("openai_codex_oauth_native",),
        ).fetchone()[0] == 1
    with connect(library) as conn:
        conn.execute(
            "UPDATE provider_queue_states SET paused_until=?, retry_after_seconds=0 WHERE provider=?",
            ("2000-01-01T00:00:00+00:00", "openai_codex_oauth_native"),
        )
        conn.commit()
    restarted = GenerationJobRepository(library)
    assert restarted.get_provider_queue_state("openai_codex_oauth_native").backoff_seconds == 300
    next_incident = restarted.record_provider_rate_limit("openai_codex_oauth_native")
    assert next_incident.backoff_seconds == 120


def test_synchronous_generation_guard_shares_production_cap(tmp_path):
    from backend.services import generation_queue

    held = [generation_queue._provider_slots.acquire(blocking=False) for _ in range(5)]
    assert all(held)
    try:
        with pytest.raises(GenerationJobConflict, match="concurrency limit"):
            generation_queue.run_generation_job_now(tmp_path / "library", "not-launched")
    finally:
        for acquired in held:
            if acquired:
                generation_queue._provider_slots.release()


def test_queue_worker_does_not_record_same_rate_limit_twice(tmp_path, monkeypatch):
    from backend.services import generation_queue
    from backend.services.openai_codex_native import CodexNativeRateLimitError

    library = tmp_path / "library"
    provider = "openai_codex_oauth_native"
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider=provider, prompt_text="rate limited"))
    continued = []

    def raise_recorded_rate_limit(_self, library_path, job_id):
        worker_repo = GenerationJobRepository(library_path)
        worker_repo.mark_running(job_id)
        worker_repo.mark_failed(job_id, "429 too many requests", retry_after_seconds=0)
        worker_repo.record_provider_rate_limit(provider, 0)
        raise CodexNativeRateLimitError("Generation is temporarily rate limited", retry_after_seconds=0)

    monkeypatch.setattr(generation_queue.OpenAICodexNativeProvider, "run_job", raise_recorded_rate_limit)
    monkeypatch.setattr(
        generation_queue,
        "_continue_generation_queue",
        lambda library_path, queued_provider: continued.append((library_path, queued_provider)),
    )

    generation_queue._run_job_and_continue(library, job.id, provider)

    state = repo.get_provider_queue_state(provider)
    assert state.paused is False
    assert state.retry_after_seconds == 0
    assert state.backoff_seconds == 0
    with connect(library) as conn:
        assert conn.execute(
            "SELECT incident_count FROM provider_queue_states WHERE provider=?",
            (provider,),
        ).fetchone()[0] == 1
    assert continued == [(library, provider)]


def test_synchronous_rate_limit_is_not_recorded_twice_and_schedules_resume(tmp_path, monkeypatch):
    from backend.routers import generation_jobs as generation_jobs_router
    from backend.services.openai_codex_native import CodexNativeRateLimitError

    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "rate limited",
    }).json()
    enqueued = []

    def raise_rate_limit(library_path, _job_id):
        GenerationJobRepository(library_path).record_provider_rate_limit("openai_codex_oauth_native", 0)
        raise CodexNativeRateLimitError("Generation is temporarily rate limited", retry_after_seconds=0)

    monkeypatch.setattr(generation_jobs_router, "run_generation_job_now", raise_rate_limit)
    monkeypatch.setattr(
        generation_jobs_router,
        "_continue_generation_queue",
        lambda library_path, provider: enqueued.append((library_path, provider)),
    )
    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 409
    assert enqueued == [(tmp_path / "library", "openai_codex_oauth_native")]
    state = GenerationJobRepository(tmp_path / "library").get_provider_queue_state("openai_codex_oauth_native")
    assert state.paused is False
    assert state.retry_after_seconds == 0
    assert state.backoff_seconds == 0
    with connect(tmp_path / "library") as conn:
        assert conn.execute(
            "SELECT incident_count FROM provider_queue_states WHERE provider=?",
            ("openai_codex_oauth_native",),
        ).fetchone()[0] == 1


def test_synchronous_success_continues_queued_provider_jobs(tmp_path, monkeypatch):
    from backend.routers import generation_jobs as generation_jobs_router

    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "completed synchronously",
    }).json()
    repo = GenerationJobRepository(tmp_path / "library")
    enqueued = []
    monkeypatch.setattr(generation_jobs_router, "run_generation_job_now", lambda *_args: repo.get_job(job["id"]))
    monkeypatch.setattr(
        generation_jobs_router,
        "_continue_generation_queue",
        lambda library_path, provider: enqueued.append((library_path, provider)),
    )

    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 200
    assert enqueued == [(tmp_path / "library", "openai_codex_oauth_native")]


def test_synchronous_rate_limit_preserves_409_when_queue_database_is_locked(tmp_path, monkeypatch):
    import sqlite3
    from backend.routers import generation_jobs as generation_jobs_router
    from backend.services import generation_queue
    from backend.services.openai_codex_native import CodexNativeRateLimitError

    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "rate limited with locked queue",
    }).json()

    def raise_rate_limit(_library_path, _job_id):
        raise CodexNativeRateLimitError("Generation is temporarily rate limited", retry_after_seconds=0)

    scheduled = []
    monkeypatch.setattr(generation_jobs_router, "run_generation_job_now", raise_rate_limit)
    monkeypatch.setattr(
        generation_queue,
        "enqueue_generation_jobs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")),
    )
    monkeypatch.setattr(
        generation_queue,
        "_schedule_pause_wake",
        lambda library_path, provider, delay: scheduled.append((library_path, provider, delay)),
    )

    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 409
    assert response.json()["detail"] == "Generation is temporarily rate limited"
    assert scheduled == [(
        tmp_path / "library",
        "openai_codex_oauth_native",
        generation_queue.QUEUE_RESUME_RETRY_SECONDS,
    )]


def test_synchronous_success_preserves_result_when_queue_database_is_locked(tmp_path, monkeypatch):
    import sqlite3
    from backend.routers import generation_jobs as generation_jobs_router
    from backend.services import generation_queue

    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "completed with locked queue",
    }).json()
    repo = GenerationJobRepository(tmp_path / "library")
    scheduled = []
    monkeypatch.setattr(generation_jobs_router, "run_generation_job_now", lambda *_args: repo.get_job(job["id"]))
    monkeypatch.setattr(
        generation_queue,
        "enqueue_generation_jobs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")),
    )
    monkeypatch.setattr(
        generation_queue,
        "_schedule_pause_wake",
        lambda library_path, provider, delay: scheduled.append((library_path, provider, delay)),
    )

    response = c.post(f"/api/generation-jobs/{job['id']}/run")
    assert response.status_code == 200
    assert response.json()["id"] == job["id"]
    assert scheduled == [(
        tmp_path / "library",
        "openai_codex_oauth_native",
        generation_queue.QUEUE_RESUME_RETRY_SECONDS,
    )]


def test_queue_resume_retries_after_transient_database_error(tmp_path, monkeypatch):
    import sqlite3
    from backend.services import generation_queue

    scheduled = []
    def fail_enqueue(*_args, **_kwargs):
        raise sqlite3.OperationalError("temporarily locked")

    monkeypatch.setattr(
        generation_queue,
        "enqueue_generation_jobs",
        fail_enqueue,
    )
    monkeypatch.setattr(
        generation_queue,
        "_schedule_pause_wake",
        lambda library_path, provider, delay: scheduled.append((library_path, provider, delay)),
    )

    generation_queue._continue_generation_queue(tmp_path / "library", "openai_codex_oauth_native")
    assert scheduled == [(
        tmp_path / "library",
        "openai_codex_oauth_native",
        generation_queue.QUEUE_RESUME_RETRY_SECONDS,
    )]


def test_generation_job_list_includes_all_active_sets_and_paused_providers(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    created = [
        repo.create_job_set(GenerationJobCreate(provider="test_provider", prompt_text=f"set {index}"), 10)
        for index in range(11)
    ]
    repo.record_provider_rate_limit("openai_codex_oauth_native", 60)

    listed = repo.list_jobs(limit=100)
    assert len(listed.jobs) == 100
    assert listed.status_counts.queued == 110
    assert {item.generation_group_id for item in listed.generation_sets} == {
        item.generation_group_id for item in created
    }
    assert all(item.jobs == [] for item in listed.generation_sets)
    assert [state.provider for state in listed.provider_queue_states] == ["openai_codex_oauth_native"]


def test_generation_job_api_preserves_exact_global_status_counts(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "queued result",
    })
    assert created.status_code == 200

    listed = c.get("/api/generation-jobs?limit=1")
    assert listed.status_code == 200
    assert listed.json()["status_counts"] == {
        "queued": 1,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "accepted": 0,
        "discarded": 0,
        "cancelled": 0,
    }


def test_generation_job_source_filter_excludes_unrelated_active_generation_sets(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    other_source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")
    source_set = repo.create_job_set(GenerationJobCreate(
        source_item_id=source_item["id"],
        provider="test_provider",
        prompt_text="source set",
    ), 3)
    repo.create_job_set(GenerationJobCreate(
        source_item_id=other_source_item["id"],
        provider="test_provider",
        prompt_text="other source set",
    ), 3)

    response = c.get(
        "/api/generation-jobs",
        params={"source_item_id": source_item["id"]},
    )

    assert response.status_code == 200
    assert {
        item["generation_group_id"] for item in response.json()["generation_sets"]
    } == {source_set.generation_group_id}


def test_generation_job_api_filters_by_source_item_with_status_and_pagination(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    other_source_item = create_source_item(c)
    repo = GenerationJobRepository(tmp_path / "library")

    older_failed = repo.create_job(GenerationJobCreate(
        source_item_id=source_item["id"],
        provider="manual_upload",
        prompt_text="older failed",
    ))
    newer_failed = repo.create_job(GenerationJobCreate(
        source_item_id=source_item["id"],
        provider="manual_upload",
        prompt_text="newer failed",
    ))
    queued = repo.create_job(GenerationJobCreate(
        source_item_id=source_item["id"],
        provider="manual_upload",
        prompt_text="queued",
    ))
    other_failed = repo.create_job(GenerationJobCreate(
        source_item_id=other_source_item["id"],
        provider="manual_upload",
        prompt_text="other failed",
    ))
    for job in (older_failed, newer_failed, other_failed):
        repo.mark_failed(job.id, "test failure")
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET created_at=? WHERE id=?",
            ("2026-01-01T00:00:00+00:00", older_failed.id),
        )
        conn.execute(
            "UPDATE generation_jobs SET created_at=? WHERE id=?",
            ("2026-01-02T00:00:00+00:00", newer_failed.id),
        )
        conn.commit()

    source_only = c.get(
        "/api/generation-jobs",
        params={"source_item_id": source_item["id"]},
    )
    assert source_only.status_code == 200
    assert source_only.json()["total"] == 3
    assert {job["id"] for job in source_only.json()["jobs"]} == {
        older_failed.id,
        newer_failed.id,
        queued.id,
    }

    filtered_page = c.get(
        "/api/generation-jobs",
        params={
            "source_item_id": source_item["id"],
            "status": "failed",
            "limit": 1,
            "offset": 1,
        },
    )
    assert filtered_page.status_code == 200
    payload = filtered_page.json()
    assert payload["total"] == 2
    assert [job["id"] for job in payload["jobs"]] == [older_failed.id]
    assert payload["status_counts"] == {
        "queued": 1,
        "running": 0,
        "succeeded": 0,
        "failed": 3,
        "accepted": 0,
        "discarded": 0,
        "cancelled": 0,
    }
