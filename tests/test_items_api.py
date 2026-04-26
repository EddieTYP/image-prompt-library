from fastapi.testclient import TestClient
from io import BytesIO
from PIL import Image
from backend.main import create_app
from backend.db import connect


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def png_bytes(size=(32, 24), color=(120, 40, 220)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


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


def test_items_list_limit_allows_gallery_overview_scale(tmp_path):
    c = client(tmp_path)
    for idx in range(230):
        c.post("/api/items", json=create_payload(title=f"Overview Item {idx}", cluster_name=f"Cluster {idx % 7}"))
    listed = c.get("/api/items", params={"limit": 300}).json()
    assert listed["total"] == 230
    assert listed["limit"] == 300
    assert len(listed["items"]) == 230


def test_patch_favorite_and_archive_item(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    c.post(
        f"/api/items/{created['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
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
    assert c.get("/api/clusters").json() == []
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0] == 0
    assert {tag["name"]: tag["count"] for tag in c.get("/api/tags").json()} == {"glass": 0, "vista": 0}


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


def test_image_upload_persists_result_and_reference_roles(tmp_path):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    result = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
    reference = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "reference_image"},
        files={"file": ("reference.png", png_bytes(color=(1, 2, 3)), "image/png")},
    )
    invalid = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "other"},
        files={"file": ("other.png", png_bytes(color=(4, 5, 6)), "image/png")},
    )
    detail = c.get(f"/api/items/{item['id']}").json()
    assert result.status_code == 200
    assert reference.status_code == 200
    assert invalid.status_code == 400
    assert [image["role"] for image in detail["images"]] == ["result_image", "reference_image"]


def test_result_image_is_primary_even_when_reference_uploaded_first(tmp_path):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    reference = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "reference_image"},
        files={"file": ("reference.png", png_bytes(color=(1, 2, 3)), "image/png")},
    ).json()
    result = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(color=(4, 5, 6)), "image/png")},
    ).json()

    listed = c.get("/api/items").json()["items"][0]
    detail = c.get(f"/api/items/{item['id']}").json()
    cluster = c.get("/api/clusters").json()[0]

    assert reference["role"] == "reference_image"
    assert result["role"] == "result_image"
    assert listed["first_image"]["id"] == result["id"]
    assert detail["first_image"]["id"] == result["id"]
    assert detail["images"][0]["id"] == result["id"]
    assert cluster["preview_images"] == [result["thumb_path"]]


def test_editing_last_item_out_of_collection_removes_empty_collection(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(cluster_name="Old Collection")).json()
    assert [cluster["name"] for cluster in c.get("/api/clusters").json()] == ["Old Collection"]

    patched = c.patch(f"/api/items/{created['id']}", json={"cluster_name": "New Collection"}).json()

    assert patched["cluster"]["name"] == "New Collection"
    assert [cluster["name"] for cluster in c.get("/api/clusters").json()] == ["New Collection"]
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT name FROM clusters").fetchall()[0]["name"] == "New Collection"


def test_listing_clusters_removes_existing_archived_only_collections(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(cluster_name="Legacy Empty Collection")).json()
    c.delete(f"/api/items/{created['id']}")
    with connect(tmp_path / "library") as conn:
        archived_cluster_id = conn.execute("SELECT cluster_id FROM items WHERE id=?", (created["id"],)).fetchone()["cluster_id"]
        old_name = "Legacy Empty Collection"
        conn.execute("INSERT INTO clusters(id, name, created_at, updated_at) VALUES(?, ?, datetime('now'), datetime('now'))", (archived_cluster_id or "clu_legacy_empty", old_name))
        conn.execute("UPDATE items SET cluster_id=? WHERE id=?", (archived_cluster_id or "clu_legacy_empty", created["id"]))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM clusters WHERE name=?", (old_name,)).fetchone()[0] == 1

    assert c.get("/api/clusters").json() == []
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM clusters WHERE name=?", (old_name,)).fetchone()[0] == 0
        assert conn.execute("SELECT cluster_id FROM items WHERE id=?", (created["id"],)).fetchone()["cluster_id"] is None


def test_create_simplified_prompt_adds_traditional_prompt(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(prompts=[{"language": "zh_hans", "text": "红龙云图"}])).json()
    prompts = {p["language"]: p["text"] for p in created["prompts"]}
    assert prompts["zh_hans"] == "红龙云图"
    assert prompts["zh_hant"] == "紅龍雲圖"
    assert c.get("/api/items", params={"q": "紅龍雲圖"}).json()["total"] == 1
