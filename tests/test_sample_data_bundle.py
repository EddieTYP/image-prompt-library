import json
import subprocess
import zipfile
from pathlib import Path

from PIL import Image

from backend.repositories import ItemRepository
from backend.services.import_sample_bundle import import_sample_bundle

ROOT = Path(__file__).resolve().parents[1]


def test_sample_data_manifests_are_localized_and_truthful():
    manifest_dir = ROOT / "sample-data" / "manifests"
    manifests = {lang: json.loads((manifest_dir / f"{lang}.json").read_text()) for lang in ("en", "zh_hans", "zh_hant")}

    assert set(manifests) == {"en", "zh_hans", "zh_hant"}
    assert len(manifests["en"]["items"]) == 162
    assert len(manifests["zh_hans"]["items"]) == 162
    assert len(manifests["zh_hant"]["items"]) == 162
    assert len(manifests["en"]["collections"]) == 10
    assert {collection["id"] for collection in manifests["en"]["collections"]} == {
        collection["id"] for collection in manifests["zh_hant"]["collections"]
    }
    assert "wuyoscar/gpt_image_2_skill" in manifests["en"]["source"]["name"]
    assert manifests["en"]["source"]["license"] == "CC BY 4.0"

    zh_hant_fallback_ids = {
        item["id"]
        for item in manifests["zh_hant"]["items"]
        if item["prompts"] and {prompt["language"] for prompt in item["prompts"]} == {"en"}
    }
    zh_hans_fallback_ids = {
        item["id"]
        for item in manifests["zh_hans"]["items"]
        if item["prompts"] and {prompt["language"] for prompt in item["prompts"]} == {"en"}
    }
    assert zh_hant_fallback_ids, "sample data should keep English-only source entries as English instead of inventing Chinese prompts"
    assert zh_hant_fallback_ids == zh_hans_fallback_ids


def test_sample_data_attribution_documents_third_party_license_boundary():
    attribution = (ROOT / "sample-data" / "ATTRIBUTION.md").read_text()
    readme = (ROOT / "sample-data" / "README.md").read_text()

    assert "wuyoscar/gpt_image_2_skill" in attribution
    assert "CC BY 4.0" in attribution
    assert "No additional restrictions" in attribution
    assert "The Image Prompt Library code license does not apply" in attribution
    assert "GitHub Release asset" in readme
    assert "./scripts/install-sample-data.sh en" in readme


def test_import_sample_bundle_loads_manifest_assets_and_is_idempotent(tmp_path: Path):
    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "one.png"
    Image.new("RGB", (16, 12), "red").save(image_path)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "id": "fixture-sample",
        "language": "zh_hant",
        "source": {"name": "fixture", "license": "CC BY 4.0"},
        "collections": [{"id": "visual", "name": "視覺設計", "names": {"en": "Visual Design", "zh_hant": "視覺設計"}}],
        "items": [{
            "id": "fixture-001",
            "title": "Fixture image",
            "slug": "fixture-image",
            "collection_id": "visual",
            "image": "images/one.png",
            "source_name": "fixture source",
            "source_url": "https://example.test/source",
            "author": "fixture author",
            "license": "CC BY 4.0",
            "tags": ["sample"],
            "prompts": [{"language": "zh_hant", "text": "一個紅色方塊", "is_primary": True}],
        }],
    }), encoding="utf-8")

    first = import_sample_bundle(manifest, assets, tmp_path / "library")
    second = import_sample_bundle(manifest, assets, tmp_path / "library")

    assert first.item_count == 1
    assert first.image_count == 1
    assert second.item_count == 0
    assert second.image_count == 0
    items = ItemRepository(tmp_path / "library").list_items(limit=10).items
    assert len(items) == 1
    assert items[0].cluster.name == "視覺設計"
    assert items[0].first_image is not None
    assert items[0].prompts[0].language == "zh_hant"
    detail = ItemRepository(tmp_path / "library").get_item(items[0].id)
    assert detail is not None
    assert "CC BY 4.0" in (detail.notes or "")
    assert "Original source URL" not in (detail.notes or "")
    assert "Original source file" not in (detail.notes or "")
    assert len(detail.notes or "") < 180


def test_install_sample_data_script_supports_local_zip_override(tmp_path: Path):
    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), "blue").save(image_dir / "fixture.png")
    manifest = tmp_path / "fixture-manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "id": "fixture-installer",
        "language": "en",
        "source": {"name": "fixture", "license": "CC BY 4.0"},
        "collections": [{"id": "demo", "name": "Demo", "names": {"en": "Demo"}}],
        "items": [{
            "id": "fixture-installer-001",
            "title": "Installer fixture",
            "slug": "installer-fixture",
            "collection_id": "demo",
            "image": "images/fixture.png",
            "source_name": "fixture",
            "tags": ["sample"],
            "prompts": [{"language": "en", "text": "A blue square", "is_primary": True}],
        }],
    }), encoding="utf-8")
    zip_path = tmp_path / "sample-images.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(image_dir / "fixture.png", "images/fixture.png")

    library = tmp_path / "library"
    result = subprocess.run(
        [str(ROOT / "scripts" / "install-sample-data.sh"), "en"],
        cwd=ROOT,
        env={
            **__import__("os").environ,
            "IMAGE_PROMPT_LIBRARY_PATH": str(library),
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
        },
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Imported 1 items" in result.stdout
    assert ItemRepository(library).list_items(limit=5).total == 1
