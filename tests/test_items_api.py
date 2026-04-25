from fastapi.testclient import TestClient
from backend.main import create_app


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def create_payload(**overrides):
    payload = {
        "title": "Dream Glass Teahouse",
        "model": "ChatGPT Image2",
        "cluster_name": "Architecture",
        "tags": ["glass", "vista"],
        "prompts": [
            {"language": "zh_hant", "text": "夢幻玻璃茶室，晨光穿過霧氣", "is_primary": True},
            {"language": "en", "text": "A dreamy glass teahouse in morning mist"},
        ],
        "source_name": "fixture",
        "source_url": "https://example.test/item",
    }
    payload.update(overrides)
    return payload


def test_create_get_search_and_filter_item(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    assert created["title"] == "Dream Glass Teahouse"
    assert created["cluster"]["name"] == "Architecture"
    assert {t["name"] for t in created["tags"]} == {"glass", "vista"}

    detail = c.get(f"/api/items/{created['id']}").json()
    assert len(detail["prompts"]) == 2
    listed = c.get("/api/items").json()["items"][0]
    assert {p["language"]: p["text"] for p in listed["prompts"]} == {
        "zh_hant": "夢幻玻璃茶室，晨光穿過霧氣",
        "en": "A dreamy glass teahouse in morning mist",
    }

    assert c.get("/api/items", params={"q": "Teahouse"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "玻璃茶室"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "morning mist"}).json()["total"] == 1
    assert c.get("/api/items", params={"tag": "vista"}).json()["total"] == 1
    assert c.get("/api/items", params={"cluster": created["cluster"]["id"]}).json()["total"] == 1


def test_patch_favorite_and_archive_item(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    patched = c.patch(f"/api/items/{created['id']}", json={"title": "Updated", "favorite": True, "rating": 4}).json()
    assert patched["title"] == "Updated"
    assert patched["favorite"] is True
    assert patched["rating"] == 4
    toggled = c.post(f"/api/items/{created['id']}/favorite").json()
    assert toggled["favorite"] is False
    deleted = c.delete(f"/api/items/{created['id']}").json()
    assert deleted["archived"] is True
    assert c.get("/api/items").json()["total"] == 0
    assert c.get("/api/items", params={"archived": True}).json()["total"] == 1


def test_clusters_tags_and_config(tmp_path):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    clusters = c.get("/api/clusters").json()
    assert clusters[0]["name"] == "Architecture"
    assert clusters[0]["count"] == 1
    tags = c.get("/api/tags").json()
    assert {t["name"] for t in tags} >= {"glass", "vista"}
    cfg = c.get("/api/config").json()
    assert cfg["database_path"].endswith("db.sqlite")
    assert c.get("/api/health").json()["ok"] is True


def test_media_route_does_not_expose_database(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    assert c.get("/media/db.sqlite").status_code == 404


def test_media_route_does_not_follow_allowed_dir_symlink_to_database(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    library = tmp_path / "library"
    leak = library / "originals" / "leak"
    leak.parent.mkdir(parents=True, exist_ok=True)
    leak.symlink_to(library / "db.sqlite")
    assert c.get("/media/originals/leak").status_code == 404


def test_punctuation_only_search_does_not_error(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    response = c.get("/api/items", params={"q": '"'})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_missing_item_mutations_return_404(tmp_path):
    c = client(tmp_path)
    assert c.delete("/api/items/missing").status_code == 404
    assert c.post("/api/items/missing/favorite").status_code == 404
    assert c.patch("/api/items/missing", json={"tags": ["ghost"]}).status_code == 404
    assert c.patch("/api/items/missing", json={"prompts": [{"language": "en", "text": "ghost"}]}).status_code == 404


def test_upload_to_missing_item_returns_404_without_orphan_files(tmp_path):
    c = client(tmp_path)
    response = c.post("/api/items/missing/images", files={"file": ("sample.png", b"not an image", "image/png")})
    assert response.status_code == 404
    library = tmp_path / "library"
    assert not [p for name in ("originals", "thumbs", "previews") if (library / name).exists() for p in (library / name).rglob("*")]


def test_create_simplified_prompt_adds_traditional_prompt(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(prompts=[{"language": "zh_hans", "text": "红龙云图"}])).json()
    prompts = {p["language"]: p["text"] for p in created["prompts"]}
    assert prompts["zh_hans"] == "红龙云图"
    assert prompts["zh_hant"] == "紅龍雲圖"
    assert c.get("/api/items", params={"q": "紅龍雲圖"}).json()["total"] == 1
