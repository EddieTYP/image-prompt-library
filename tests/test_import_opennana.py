import json
from pathlib import Path
from PIL import Image
from backend.db import init_db
from backend.repositories import ItemRepository
from backend.services.import_opennana import import_opennana


def test_import_opennana_fixture(tmp_path: Path):
    source_dir = tmp_path / "source"
    image_dir = source_dir / "images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (64, 64), "red").save(image_dir / "one.png")
    gallery = {"items": [{
        "slug": "red-dragon",
        "title": "Red Dragon",
        "topic": "Fantasy",
        "tags": ["dragon", "poster"],
        "prompt_zh_tw": "紅龍海報",
        "prompt_zh_cn": "红龙海报",
        "prompt_en": "Red dragon poster",
        "image": "images/one.png",
        "source_url": "https://example.test/red",
    }]}
    gallery_path = source_dir / "gallery.json"
    gallery_path.write_text(json.dumps(gallery), encoding="utf-8")
    library = tmp_path / "library"
    init_db(library)
    result = import_opennana(gallery_path, library)
    assert result.item_count == 1
    assert result.image_count == 1
    repo = ItemRepository(library)
    listed = repo.list_items(q="紅龍")
    assert listed.total == 1
    detail = repo.get_item(listed.items[0].id)
    assert detail.cluster.name == "Fantasy"
    assert detail.images and (library / detail.images[0].thumb_path).exists()
