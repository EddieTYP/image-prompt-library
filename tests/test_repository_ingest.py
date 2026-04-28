from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app


def make_fixture_repo(root: Path) -> Path:
    repo = root / "fixture-repo"
    image_dir = repo / "images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (16, 12), "purple").save(image_dir / "neon-cat.png")
    (repo / "gallery.md").write_text(
        """# Cyber Animals

## Neon Cat

![Generated result](images/neon-cat.png)

```text
A neon cyberpunk cat sleeping on a glowing keyboard
```
""",
        encoding="utf-8",
    )
    return repo


def test_repository_ingest_stages_markdown_prompt_and_media_then_accepts_to_library(tmp_path):
    repo = make_fixture_repo(tmp_path)
    library = tmp_path / "library"
    c = TestClient(create_app(library_path=library))

    result = c.post("/api/import-drafts/repository", json={
        "path": str(repo),
        "repo_url": "https://github.com/example/prompt-repo",
        "source_ref": "abc123",
    })

    assert result.status_code == 200
    payload = result.json()
    assert payload["draft_count"] == 1
    assert payload["status"] == "completed"
    draft = payload["drafts"][0]
    assert draft["status"] == "staged"
    assert draft["title"] == "Neon Cat"
    assert draft["source_type"] == "repository"
    assert draft["source_name"] == "prompt-repo"
    assert draft["source_ref"] == "abc123"
    assert draft["source_path"] == "gallery.md"
    assert draft["suggested_cluster_name"] == "Cyber Animals"
    assert draft["source_url"] == "https://github.com/example/prompt-repo/blob/abc123/gallery.md"
    assert draft["prompts"] == [{
        "language": "en",
        "text": "A neon cyberpunk cat sleeping on a glowing keyboard",
        "is_primary": True,
        "is_original": True,
        "provenance": {
            "kind": "source",
            "source_language": "en",
            "derived_from": None,
            "method": None,
        },
    }]
    assert draft["media"][0]["original_path"] == "images/neon-cat.png"
    assert draft["media"][0]["staged_path"].startswith("import-staging/")
    assert (library / draft["media"][0]["staged_path"]).is_file()
    assert draft["media"][0]["width"] == 16
    assert draft["media"][0]["height"] == 12
    assert draft["media"][0]["file_sha256"]

    accepted = c.post(f"/api/import-drafts/{draft['id']}/accept")
    assert accepted.status_code == 200
    item = accepted.json()["item"]
    assert item["title"] == "Neon Cat"
    assert item["source_url"] == "https://github.com/example/prompt-repo/blob/abc123/gallery.md"
    assert item["cluster"]["name"] == "Cyber Animals"
    assert item["images"][0]["role"] == "result_image"
    assert item["images"][0]["original_path"].startswith("originals/")
    assert item["images"][0]["thumb_path"].startswith("thumbs/")
    assert item["images"][0]["preview_path"].startswith("previews/")


def test_repository_ingest_marks_duplicate_drafts_by_source_url(tmp_path):
    repo = make_fixture_repo(tmp_path)
    c = TestClient(create_app(library_path=tmp_path / "library"))

    first = c.post("/api/import-drafts/repository", json={"path": str(repo), "repo_url": "https://github.com/example/prompt-repo", "source_ref": "main"}).json()
    accepted = c.post(f"/api/import-drafts/{first['drafts'][0]['id']}/accept").json()

    second = c.post("/api/import-drafts/repository", json={"path": str(repo), "repo_url": "https://github.com/example/prompt-repo", "source_ref": "main"})

    assert second.status_code == 200
    draft = second.json()["drafts"][0]
    assert draft["status"] == "duplicate"
    assert draft["duplicate_of_item_id"] == accepted["item"]["id"]


def test_repository_ingest_rejects_paths_outside_selected_source_root(tmp_path):
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (8, 8), "red").save(outside)
    (repo / "gallery.md").write_text(
        f"""# Bad Paths

## Escaping Image

![Bad](../{outside.name})

```text
This should not stage the escaping image
```
""",
        encoding="utf-8",
    )
    c = TestClient(create_app(library_path=tmp_path / "library"))

    result = c.post("/api/import-drafts/repository", json={"path": str(repo)})

    assert result.status_code == 200
    draft = result.json()["drafts"][0]
    assert draft["media"] == []
    assert any("escapes repository root" in warning for warning in draft["warnings"])
