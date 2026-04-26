import json
from pathlib import Path

from PIL import Image

from backend.db import init_db
from backend.repositories import ItemRepository
from backend.services.import_gpt_image_2_skill import import_gpt_image_2_skill


def _write_source_fixture(root: Path) -> Path:
    docs = root / "docs"
    gaming = docs / "gaming"
    gaming.mkdir(parents=True)
    Image.new("RGB", (80, 48), "purple").save(gaming / "retro-rpg.png")
    Image.new("RGB", (64, 64), "orange").save(docs / "poster.png")
    records = [
        {
            "id": "reddit-10",
            "platform": "reddit",
            "category": "Gaming",
            "title": "Retro Japanese town pixel RPG",
            "source_title": "Retro Video Games In Japan (Prompts Included)",
            "source_url": "https://www.reddit.com/r/midjourney/comments/example/",
            "source_excerpt": "Isometric pixel art depiction of a traditional Japanese village.",
            "prompt": "Create an isometric pixel-art RPG screenshot of a traditional Japanese village.",
            "size": "1536x1024",
            "file": "docs/gaming/retro-rpg.png",
        },
        {
            "id": "xhs-01",
            "platform": "xiaohongshu",
            "category": "Typography & Posters",
            "title": "Epic silhouette worldbuilding poster",
            "source_title": "Epic poster prompt",
            "source_url": "https://www.xiaohongshu.com/explore/example",
            "source_excerpt": "Layered silhouette poster composition.",
            "prompt": "Create a layered silhouette worldbuilding poster.",
            "file": "docs/poster.png",
        },
    ]
    (docs / "community-prompt-picks.json").write_text(json.dumps(records), encoding="utf-8")
    return root


def test_import_gpt_image_2_skill_creates_attributed_items_and_images(tmp_path: Path):
    source = _write_source_fixture(tmp_path / "gpt_image_2_skill")
    library = tmp_path / "library"
    init_db(library)

    result = import_gpt_image_2_skill(source, library)

    assert result.item_count == 2
    assert result.image_count == 2
    repo = ItemRepository(library)
    listed = repo.list_items(limit=10)
    assert listed.total == 2
    detail = repo.get_item(repo.list_items(q="Retro Japanese").items[0].id)
    assert detail.cluster.name == "Gaming"
    assert detail.source_name == "wuyoscar/gpt_image_2_skill"
    assert detail.source_url == "https://www.reddit.com/r/midjourney/comments/example/"
    assert detail.author == "reddit"
    assert detail.images and (library / detail.images[0].thumb_path).exists()
    assert detail.images[0].role == "result_image"
    prompt = next(prompt for prompt in detail.prompts if prompt.language == "en")
    assert "isometric pixel-art RPG" in prompt.text
    assert "CC BY 4.0" in (detail.notes or "")
    assert "Retro Video Games In Japan" in (detail.notes or "")
    assert "Imported from wuyoscar/gpt_image_2_skill" in (detail.notes or "")


def test_import_gpt_image_2_skill_is_idempotent_by_record_id(tmp_path: Path):
    source = _write_source_fixture(tmp_path / "gpt_image_2_skill")
    library = tmp_path / "library"

    first = import_gpt_image_2_skill(source, library)
    second = import_gpt_image_2_skill(source, library)

    repo = ItemRepository(library)
    assert first.item_count == 2
    assert first.image_count == 2
    assert second.item_count == 0
    assert second.image_count == 0
    assert repo.list_items(limit=10).total == 2
