from pathlib import Path

from PIL import Image

from backend.db import connect, init_db
from backend.repositories import ItemRepository
from backend.services.import_gpt_image_2_skill import import_gpt_image_2_skill, load_full_gallery_records


def _write_full_gallery_fixture(root: Path, count: int = 3) -> Path:
    docs = root / "docs"
    refs = root / "skills" / "gpt-image" / "references"
    gaming = docs / "gaming"
    refs.mkdir(parents=True)
    gaming.mkdir(parents=True)
    rows = []
    zh_sections = []
    for idx in range(1, count + 1):
        image_path = f"docs/gaming/sample-{idx}.png"
        Image.new("RGB", (80 + idx, 48 + idx), "purple").save(root / image_path)
        rows.append(
            f"""### No. {idx} · Sample prompt {idx}

- Image: `{image_path}`

  <img src="../../../{image_path}" alt="sample {idx}" width="420"/>
- Metadata: Gaming · `landscape` · `1536x1024` · Curated

```text
Create an English sample prompt number {idx} with a traditional Japanese village and glowing UI.
```
"""
        )
        zh_sections.append(
            f"""#### 游戏样本 {idx}

<p align="center">
<a href="{image_path}"><img src="{image_path}" width="460" alt="简中样本 {idx}"/></a>
</p>

<p align="center"><sub><code>"landscape"</code> · <code>"high"</code> · <code>"Curated"</code></sub></p>

<details>
<summary><strong>📝 提示词</strong></summary>

```text
创建第{idx}个红龙云图，包含发光界面与传统村庄。
```

</details>
"""
        )
    (refs / "gallery-gaming.md").write_text("# 🎮 Gaming\n\nRange: No. 1–3 · Count: 3\n\n" + "\n".join(rows), encoding="utf-8")
    (refs / "gallery.md").write_text(
        "# GPT Image 2 Prompt Gallery Index\n\n| Category | File | Range | Count |\n|---|---|---:|---:|\n| 🎮 Gaming | [`gallery-gaming.md`](gallery-gaming.md) | No. 1–3 | 3 |\n",
        encoding="utf-8",
    )
    (root / "README.zh.md").write_text("\n---\n".join(zh_sections), encoding="utf-8")
    return root


def test_load_full_gallery_records_parses_canonical_category_markdown_with_chinese_editions(tmp_path: Path):
    source = _write_full_gallery_fixture(tmp_path / "gpt_image_2_skill", count=3)

    records = load_full_gallery_records(source)

    assert [record["number"] for record in records] == [1, 2, 3]
    first = records[0]
    assert first["title"] == "Sample prompt 1"
    assert first["category"] == "Gaming"
    assert first["file"] == "docs/gaming/sample-1.png"
    assert "English sample prompt number 1" in first["prompt_en"]
    assert first["prompt_zh_hans"] == "创建第1个红龙云图，包含发光界面与传统村庄。"
    assert first["prompt_zh_hant"] == "創建第1個紅龍雲圖，包含發光界面與傳統村莊。"
    assert first["category_zh_hans"] == "游戏样本 1"
    assert first["category_zh_hant"] == "遊戲樣本 1"


def test_import_gpt_image_2_skill_imports_full_multilingual_catalog_by_default(tmp_path: Path):
    source = _write_full_gallery_fixture(tmp_path / "gpt_image_2_skill", count=3)
    library = tmp_path / "library"
    init_db(library)

    result = import_gpt_image_2_skill(source, library)

    assert result.item_count == 3
    assert result.image_count == 3
    repo = ItemRepository(library)
    listed = repo.list_items(limit=10)
    assert listed.total == 3
    with connect(library) as conn:
        item_id = conn.execute("SELECT id FROM items WHERE slug=?", ("gpt-image-2-skill-no-1",)).fetchone()[0]
    detail = repo.get_item(item_id)
    assert detail.slug == "gpt-image-2-skill-no-1"
    assert detail.cluster.name == "Gaming"
    assert detail.source_name == "wuyoscar/gpt_image_2_skill"
    assert detail.author == "wuyoscar/gpt_image_2_skill"
    assert detail.images and (library / detail.images[0].thumb_path).exists()
    assert detail.images[0].role == "result_image"
    prompts = {prompt.language: prompt.text for prompt in detail.prompts}
    assert "English sample prompt number 1" in prompts["en"]
    assert prompts["zh_hans"] == "创建第1个红龙云图，包含发光界面与传统村庄。"
    assert prompts["zh_hant"] == "創建第1個紅龍雲圖，包含發光界面與傳統村莊。"
    assert "Full catalog No. 1" in (detail.notes or "")
    assert "CC BY 4.0" in (detail.notes or "")


def test_import_gpt_image_2_skill_supports_language_specific_sample_editions(tmp_path: Path):
    source = _write_full_gallery_fixture(tmp_path / "gpt_image_2_skill", count=2)

    zh_hant_library = tmp_path / "library-zh-hant"
    zh_hant_result = import_gpt_image_2_skill(source, zh_hant_library, edition="zh_hant")
    zh_hant_repo = ItemRepository(zh_hant_library)
    with connect(zh_hant_library) as conn:
        zh_hant_item_id = conn.execute("SELECT id FROM items WHERE slug=?", ("gpt-image-2-skill-no-1-zh-hant",)).fetchone()[0]
    zh_hant_detail = zh_hant_repo.get_item(zh_hant_item_id)
    zh_hant_prompts = {prompt.language: prompt.text for prompt in zh_hant_detail.prompts}
    assert zh_hant_result.item_count == 2
    assert zh_hant_detail.cluster.name == "遊戲樣本 1"
    assert set(zh_hant_prompts) == {"zh_hant"}
    assert zh_hant_prompts["zh_hant"] == "創建第1個紅龍雲圖，包含發光界面與傳統村莊。"

    zh_hans_library = tmp_path / "library-zh-hans"
    import_gpt_image_2_skill(source, zh_hans_library, edition="zh_hans")
    zh_hans_repo = ItemRepository(zh_hans_library)
    with connect(zh_hans_library) as conn:
        zh_hans_item_id = conn.execute("SELECT id FROM items WHERE slug=?", ("gpt-image-2-skill-no-1-zh-hans",)).fetchone()[0]
    zh_hans_detail = zh_hans_repo.get_item(zh_hans_item_id)
    zh_hans_prompts = {prompt.language: prompt.text for prompt in zh_hans_detail.prompts}
    assert zh_hans_detail.cluster.name == "游戏样本 1"
    assert set(zh_hans_prompts) == {"zh_hans"}
    assert zh_hans_prompts["zh_hans"] == "创建第1个红龙云图，包含发光界面与传统村庄。"

    en_library = tmp_path / "library-en"
    import_gpt_image_2_skill(source, en_library, edition="en")
    en_repo = ItemRepository(en_library)
    with connect(en_library) as conn:
        en_item_id = conn.execute("SELECT id FROM items WHERE slug=?", ("gpt-image-2-skill-no-1-en",)).fetchone()[0]
    en_detail = en_repo.get_item(en_item_id)
    en_prompts = {prompt.language: prompt.text for prompt in en_detail.prompts}
    assert en_detail.cluster.name == "Gaming"
    assert set(en_prompts) == {"en"}
    assert "English sample prompt number 1" in en_prompts["en"]


def test_import_gpt_image_2_skill_is_idempotent_by_gallery_number(tmp_path: Path):
    source = _write_full_gallery_fixture(tmp_path / "gpt_image_2_skill", count=2)
    library = tmp_path / "library"

    first = import_gpt_image_2_skill(source, library)
    second = import_gpt_image_2_skill(source, library)

    repo = ItemRepository(library)
    assert first.item_count == 2
    assert first.image_count == 2
    assert second.item_count == 0
    assert second.image_count == 0
    assert repo.list_items(limit=10).total == 2
