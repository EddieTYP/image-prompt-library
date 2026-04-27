import json
import zipfile
from pathlib import Path

from PIL import Image

from backend.repositories import ItemRepository
from backend.services.import_sample_bundle import import_sample_bundle

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "sample-data" / "manifests" / "awesome-gpt-image-2"


def test_awesome_gpt_image_2_manifest_is_second_sample_package():
    manifest = json.loads((MANIFEST_DIR / "zh_hant.json").read_text(encoding="utf-8"))

    assert manifest["id"] == "awesome-gpt-image-2-v1-zh_hant"
    assert manifest["language"] == "zh_hant"
    assert manifest["source"]["name"] == "freestylefly/awesome-gpt-image-2"
    assert manifest["source"]["url"] == "https://github.com/freestylefly/awesome-gpt-image-2"
    assert manifest["source"]["license"] == "MIT"
    assert manifest["source"]["permission_note"]
    assert len(manifest["items"]) >= 340
    assert len(manifest["collections"]) >= 10

    first = manifest["items"][0]
    assert first["slug"].startswith("sample-awesome-gpt-image-2-")
    assert first["image"].startswith("images/case")
    assert {prompt["language"] for prompt in first["prompts"]} >= {"zh_hant"}
    assert "awesome_gpt_image_2" in first["tags"]
    assert "sample_package_2" in first["tags"]

    all_prompt_text = "\n".join(
        prompt["text"]
        for item in manifest["items"]
        for prompt in item.get("prompts", [])
        if prompt.get("language") == "zh_hant"
    )
    assert "创建" not in all_prompt_text
    assert "设计" not in all_prompt_text
    assert "图像" not in all_prompt_text
    assert "简洁" not in all_prompt_text
    assert "畫面" in all_prompt_text or "設計" in all_prompt_text


def test_awesome_gpt_image_2_attribution_and_readme_are_documented():
    attribution = (ROOT / "sample-data" / "ATTRIBUTION.md").read_text(encoding="utf-8")
    readme = (ROOT / "sample-data" / "README.md").read_text(encoding="utf-8")

    assert "freestylefly/awesome-gpt-image-2" in attribution
    assert "MIT" in attribution
    assert "second sample package" in readme
    assert "awesome-gpt-image-2" in readme
    assert "image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip" in readme


def test_awesome_gpt_image_2_manifest_imports_with_sample_bundle(tmp_path: Path):
    manifest = json.loads((MANIFEST_DIR / "zh_hant.json").read_text(encoding="utf-8"))
    selected = manifest["items"][:2]

    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    for item in selected:
        Image.new("RGB", (24, 18), "purple").save(assets / item["image"])

    tiny_manifest = dict(manifest)
    tiny_manifest["items"] = selected
    manifest_path = tmp_path / "awesome-gpt-image-2-tiny.json"
    manifest_path.write_text(json.dumps(tiny_manifest, ensure_ascii=False), encoding="utf-8")

    result = import_sample_bundle(manifest_path, assets, tmp_path / "library")

    assert result.item_count == 2
    assert result.image_count == 2
    items = ItemRepository(tmp_path / "library").list_items(limit=5).items
    assert len(items) == 2
    assert items[0].prompts
    assert items[0].first_image is not None
