from fastapi.testclient import TestClient
from backend.main import create_app
from backend.db import connect


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def draft_payload(**overrides):
    payload = {
        "source_type": "repository",
        "source_name": "fixture repo",
        "source_url": "https://github.com/example/prompts/blob/main/gallery.md#item-1",
        "source_ref": "abc123",
        "source_path": "gallery.md",
        "title": "Red Dragon Cloud",
        "model": "ChatGPT Image2",
        "author": "@artist",
        "suggested_cluster_name": "Fantasy",
        "suggested_tags": ["dragon", "cloud"],
        "prompts": [
            {
                "language": "zh_hans",
                "text": "红龙云图",
                "is_original": True,
                "provenance": {"kind": "source", "source_language": "zh_hans"},
            }
        ],
        "media": [
            {"url": "https://example.test/red-dragon.png", "role": "result_image", "kind": "remote"}
        ],
        "warnings": ["fixture warning"],
        "confidence": 0.82,
    }
    payload.update(overrides)
    return payload


def test_import_draft_can_be_staged_previewed_and_accepted(tmp_path):
    c = client(tmp_path)

    staged = c.post("/api/import-drafts", json=draft_payload()).json()

    assert staged["status"] == "staged"
    assert staged["title"] == "Red Dragon Cloud"
    assert staged["source_type"] == "repository"
    assert staged["source_ref"] == "abc123"
    assert staged["source_path"] == "gallery.md"
    assert staged["suggested_cluster_name"] == "Fantasy"
    assert staged["duplicate_of_item_id"] is None
    assert staged["warnings"] == ["fixture warning"]
    assert staged["media"][0]["url"] == "https://example.test/red-dragon.png"

    listed = c.get("/api/import-drafts").json()
    assert listed["total"] == 1
    assert listed["drafts"][0]["id"] == staged["id"]

    accepted = c.post(f"/api/import-drafts/{staged['id']}/accept").json()
    assert accepted["draft"]["status"] == "accepted"
    assert accepted["item"]["title"] == "Red Dragon Cloud"
    assert accepted["item"]["cluster"]["name"] == "Fantasy"
    assert {tag["name"] for tag in accepted["item"]["tags"]} == {"dragon", "cloud"}
    prompts = {prompt["language"]: prompt for prompt in accepted["item"]["prompts"]}
    assert prompts["zh_hans"]["is_original"] is True
    assert prompts["zh_hant"]["text"] == "紅龍雲圖"
    assert prompts["zh_hant"]["provenance"]["kind"] == "conversion"
    assert accepted["item"]["source_url"] == draft_payload()["source_url"]

    assert c.post(f"/api/import-drafts/{staged['id']}/accept").status_code == 409


def test_import_draft_marks_duplicate_by_source_url_and_accept_rejects_it(tmp_path):
    c = client(tmp_path)
    existing = c.post("/api/items", json={
        "title": "Existing Dragon",
        "source_name": "fixture repo",
        "source_url": draft_payload()["source_url"],
        "prompts": [{"language": "en", "text": "existing", "is_original": True}],
    }).json()

    staged = c.post("/api/import-drafts", json=draft_payload()).json()

    assert staged["status"] == "duplicate"
    assert staged["duplicate_of_item_id"] == existing["id"]
    response = c.post(f"/api/import-drafts/{staged['id']}/accept")
    assert response.status_code == 409
    assert "duplicate" in response.json()["detail"].lower()


def test_import_draft_marks_duplicate_by_normalized_prompt_text(tmp_path):
    c = client(tmp_path)
    existing = c.post("/api/items", json={
        "title": "Existing Prompt",
        "source_url": "https://example.test/different",
        "prompts": [{"language": "zh_hans", "text": "红龙云图", "is_original": True}],
    }).json()

    staged = c.post("/api/import-drafts", json=draft_payload(source_url="https://example.test/new-url")).json()

    assert staged["status"] == "duplicate"
    assert staged["duplicate_of_item_id"] == existing["id"]


def test_import_draft_tables_are_migrated(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/health").status_code == 200
    with connect(tmp_path / "library") as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "import_drafts" in tables
