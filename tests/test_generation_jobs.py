from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.db import connect
from backend.main import create_app


def png_bytes(color="orange", size=(18, 12)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def create_source_item(c):
    return c.post("/api/items", json={
        "title": "Source prompt",
        "prompts": [{"language": "en", "text": "A cinematic moonlit robot", "is_original": True}],
    }).json()


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
    assert "generation_jobs" in tables
