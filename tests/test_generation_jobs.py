from datetime import datetime, timedelta, timezone
from io import BytesIO
import base64
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
from PIL import Image

from backend.db import connect
from backend.main import create_app
from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository, _classify_error


def png_bytes(color="orange", size=(18, 12)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def test_temporary_token_refresh_errors_are_not_classified_as_auth_required():
    assert _classify_error("Token refresh is temporarily unavailable") == "provider_unavailable"


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
    (tmp_path / "library" / "generation-results").symlink_to(outside_root, target_is_directory=True)

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
    (library / "generation-results").symlink_to(wrong_results, target_is_directory=True)

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
    (library / "generation-references").symlink_to(wrong_references, target_is_directory=True)

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
    (tmp_path / "library" / "generation-results").symlink_to(outside_root, target_is_directory=True)

    response = c.post(
        f"/api/generation-jobs/{job['id']}/result",
        files={"file": ("generated.png", png_bytes("green"), "image/png")},
    )

    assert response.status_code == 409
    assert list(outside_root.rglob("*")) == []
    assert c.get(f"/api/generation-jobs/{job['id']}").json()["status"] == "queued"


def test_stage_result_rejects_nested_generation_result_symlink_before_write(tmp_path):
    c = client(tmp_path)
    existing = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "existing result"}).json()
    c.post(f"/api/generation-jobs/{existing['id']}/result", files={"file": ("existing.png", png_bytes("blue"), "image/png")})
    existing_dir = tmp_path / "library" / "generation-results" / existing["id"]
    before = sorted(path.relative_to(existing_dir).as_posix() for path in existing_dir.rglob("*"))
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "unsafe nested result write"}).json()
    (tmp_path / "library" / "generation-results" / job["id"]).symlink_to(existing_dir, target_is_directory=True)

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
    (tmp_path / "library" / "generation-references").symlink_to(outside_root, target_is_directory=True)

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
    (library / "generation-references" / "dest-job").symlink_to(wrong_reference_dir, target_is_directory=True)

    try:
        GenerationJobRepository(library)._clone_generation_result_input(job_id="dest-job", result_path=source_path)
    except GenerationJobConflict:
        pass
    else:
        raise AssertionError("expected nested reference symlink clone destination to be rejected")

    assert list(wrong_reference_dir.rglob("*")) == []


def test_discard_rejects_symlinked_generation_result_root_before_delete(tmp_path):
    c = client(tmp_path)
    job = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "unsafe symlink result"}).json()
    outside_root = tmp_path / "outside-results"
    outside_file = outside_root / job["id"] / "generated.png"
    outside_file.parent.mkdir(parents=True)
    outside_file.write_bytes(png_bytes("purple"))
    (tmp_path / "library" / "generation-results").symlink_to(outside_root, target_is_directory=True)
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
    victim_file.symlink_to(target_file)

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
    legacy_parameters = {"input_images": [{"result_path": source_path, "name": "legacy-source.png"}]}
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
    assert repaired_spec["result_path"].startswith(f"generation-references/{downstream['id']}/")
    assert (tmp_path / "library" / repaired_spec["result_path"]).is_file()
    assert repaired["metadata"]["reference_image_copies"][0]["source_result_path"] == source_path
    assert repaired["metadata"]["reference_image_repair"]["repaired_from_discard_job_id"] == source["id"]


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

    failed = repo.mark_stale_running_failed(job_id)
    retry = repo.retry_failed_job(job_id)

    assert failed.status == "failed"
    assert failed.error == "Generation took too long and may have stalled. Retry to run it again."
    assert failed.metadata["stale_running_marked_failed"] is True
    assert failed.metadata["stale_running_threshold_minutes"] == 10
    assert retry.status == "queued"
    assert retry.metadata["retry_of_generation_job_id"] == job_id


def test_queued_and_running_generation_jobs_can_be_cancelled(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    queued = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued"))
    running = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="running"))
    repo.mark_running(running.id)

    assert repo.cancel_job(queued.id).status == "cancelled"
    assert repo.cancel_job(running.id).status == "cancelled"


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
