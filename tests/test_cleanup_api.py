from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from backend.db import connect
from backend.main import create_app


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def png_bytes(size=(32, 24), color=(120, 40, 220)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def create_payload(**overrides):
    payload = {
        "title": "Cleanup Fixture",
        "model": "ChatGPT Image2",
        "cluster_name": "Cleanup",
        "tags": ["cleanup"],
        "prompts": [{"language": "en", "text": "A cleanup fixture", "is_primary": True}],
        "source_name": "fixture",
        "source_url": "https://example.test/cleanup",
    }
    payload.update(overrides)
    return payload


def test_cleanup_preview_reports_broken_image_records_and_unreferenced_files(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    item = c.post("/api/items", json=create_payload()).json()
    extra = library / "originals" / "extra.png"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"extra")
    with connect(library) as conn:
        conn.execute(
            """INSERT INTO images(id,item_id,original_path,thumb_path,preview_path,role,sort_order,created_at)
               VALUES(?,?,?,?,?,?,?,datetime('now'))""",
            ("img_broken", item["id"], "originals/missing.png", None, None, "result_image", 0),
        )
        conn.commit()

    preview = c.get("/api/cleanup/preview").json()

    assert preview["broken_image_records"][0]["image_id"] == "img_broken"
    assert preview["unreferenced_files"][0]["path"] == "originals/extra.png"
    assert (library / "originals" / "extra.png").exists()
    with connect(library) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id='img_broken'").fetchone()[0] == 1


def test_cleanup_apply_removes_only_previewed_safe_records_and_files(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    item = c.post("/api/items", json=create_payload()).json()
    uploaded = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    ).json()
    extra = library / "originals" / "extra.png"
    extra.write_bytes(b"extra")
    with connect(library) as conn:
        conn.execute(
            """INSERT INTO images(id,item_id,original_path,thumb_path,preview_path,role,sort_order,created_at)
               VALUES(?,?,?,?,?,?,?,datetime('now'))""",
            ("img_broken", item["id"], "originals/missing.png", None, None, "reference_image", 1),
        )
        conn.commit()

    result = c.post("/api/cleanup/apply", json={"remove_broken_image_records": True, "remove_unreferenced_files": True}).json()

    assert result["removed_broken_image_records"] == 1
    assert result["removed_unreferenced_files"] == 1
    assert not extra.exists()
    assert (library / uploaded["original_path"]).exists()
    with connect(library) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id='img_broken'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id=?", (uploaded["id"],)).fetchone()[0] == 1


def test_cleanup_preview_ignores_generation_results(tmp_path):
    c = client(tmp_path)
    library = tmp_path / "library"
    c.post("/api/items", json=create_payload())
    generated = library / "generation-results" / "orphan.png"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"generated")

    preview = c.get("/api/cleanup/preview").json()

    assert [record["path"] for record in preview["unreferenced_files"]] == []
    assert generated.exists()
