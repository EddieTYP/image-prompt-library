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
