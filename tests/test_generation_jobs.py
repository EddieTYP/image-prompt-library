from io import BytesIO
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
from PIL import Image

from backend.db import connect
from backend.main import create_app
from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobRepository


def png_bytes(color="orange", size=(18, 12)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def create_source_item(c, *, author=None):
    payload = {
        "title": "Source prompt",
        "prompts": [{"language": "en", "text": "A cinematic moonlit robot", "is_original": True}],
    }
    if author is not None:
        payload["author"] = author
    return c.post("/api/items", json=payload).json()


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
    enqueue_calls.clear()

    response = c.post(f"/api/generation-jobs/{job['id']}/discard-and-retry")

    assert response.status_code == 200
    payload = response.json()
    discarded = payload["discarded_job"]
    retry = payload["retry_job"]
    assert discarded["id"] == job["id"]
    assert discarded["status"] == "discarded"
    assert discarded["metadata"]["retried_by_generation_job_id"] == retry["id"]
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


def test_generation_queue_runs_at_most_two_native_jobs(tmp_path, monkeypatch):
    from backend.services import generation_queue

    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job_ids = [repo.create_job(GenerationJobCreate(
        provider="openai_codex_oauth_native",
        prompt_text=f"queued job {index}",
    )).id for index in range(3)]
    active = 0
    max_seen = 0
    completed: list[str] = []
    lock = threading.Lock()

    class FakeProvider:
        def run_job(self, library_path, job_id):
            nonlocal active, max_seen
            fake_repo = GenerationJobRepository(library_path)
            fake_repo.mark_running(job_id)
            with lock:
                active += 1
                max_seen = max(max_seen, active)
            time.sleep(0.05)
            fake_repo.stage_result(job_id, png_bytes("yellow"), "generated.png", {"fake": True})
            with lock:
                active -= 1
                completed.append(job_id)

    monkeypatch.setattr(generation_queue, "OpenAICodexNativeProvider", FakeProvider)

    generation_queue.enqueue_generation_jobs(library)
    deadline = time.time() + 3
    while time.time() < deadline:
        if len(completed) == 3:
            break
        time.sleep(0.02)

    assert sorted(completed) == sorted(job_ids)
    assert max_seen == 2
    assert [repo.get_job(job_id).status for job_id in job_ids] == ["succeeded", "succeeded", "succeeded"]
