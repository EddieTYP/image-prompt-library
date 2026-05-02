import json
import os
import shutil
import subprocess
import sys
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

    english_origin_ids = {
        item["id"]
        for item in manifests["zh_hant"]["items"]
        for prompt in item["prompts"]
        if prompt["language"] == "en" and prompt.get("is_original")
    }
    assert english_origin_ids, "sample data should preserve English as the source/original language when upstream English was original"
    for manifest in manifests.values():
        for language in ("en", "zh_hant", "zh_hans"):
            assert sum(1 for item in manifest["items"] for prompt in item["prompts"] if prompt["language"] == language) == 162


def assert_v2_prompt_provenance(manifest: dict):
    assert manifest["schema_version"] == 2
    for item in manifest["items"]:
        prompts = item.get("prompts", [])
        originals = [prompt for prompt in prompts if prompt.get("is_original")]
        assert len(originals) == 1, item["id"]
        for prompt in prompts:
            provenance = prompt.get("provenance")
            assert isinstance(provenance, dict), item["id"]
            assert provenance.get("kind") in {"source", "conversion", "translation", "manual"}
            assert provenance.get("source_language") in {"en", "zh_hant", "zh_hans"}
            if not prompt.get("is_original"):
                assert provenance.get("derived_from") in {"en", "zh_hant", "zh_hans"}


def test_sample_data_manifests_use_schema_v2_prompt_provenance():
    manifest_dir = ROOT / "sample-data" / "manifests"
    for lang in ("en", "zh_hans", "zh_hant"):
        assert_v2_prompt_provenance(json.loads((manifest_dir / f"{lang}.json").read_text(encoding="utf-8")))

def test_sample_data_attribution_documents_third_party_license_boundary():
    attribution = (ROOT / "sample-data" / "ATTRIBUTION.md").read_text()
    readme = (ROOT / "sample-data" / "README.md").read_text()

    assert "wuyoscar/gpt_image_2_skill" in attribution
    assert "CC BY 4.0" in attribution
    assert "No additional restrictions" in attribution
    assert "The Image Prompt Library code license does not apply" in attribution
    assert "sample-data-v1" in readme
    assert "image-prompt-library-sample-images-v1.zip" in readme
    assert "SHA256" in readme
    assert "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035" in readme
    assert "./scripts/install-sample-data.sh en" in readme
    assert "fill_sample_manifest_translations.py" in readme
    assert (ROOT / "backend" / "services" / "fill_sample_manifest_translations.py").exists()


def test_import_sample_bundle_loads_manifest_assets_and_is_idempotent(tmp_path: Path):
    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "one.png"
    Image.new("RGB", (16, 12), "red").save(image_path)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 2,
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
            "prompts": [{
                "language": "zh_hant",
                "text": "一個紅色方塊",
                "is_primary": True,
                "is_original": True,
                "provenance": {"kind": "source", "source_language": "zh_hant", "derived_from": None, "method": None},
            }],
        }],
    }), encoding="utf-8")

    first = import_sample_bundle(manifest, assets, tmp_path / "library")
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["items"][0]["prompts"][0]["text"] = "一個已更新的紅色方塊"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    second = import_sample_bundle(manifest, assets, tmp_path / "library")

    assert first.item_count == 1
    assert first.image_count == 1
    assert second.item_count == 0
    assert second.image_count == 0
    items = ItemRepository(tmp_path / "library").list_items(limit=10).items
    assert len(items) == 1
    assert items[0].cluster.name == "視覺設計"
    assert items[0].cluster.names == {"en": "Visual Design", "zh_hant": "視覺設計"}
    assert items[0].first_image is not None
    assert items[0].prompts[0].text == "一個已更新的紅色方塊"
    assert items[0].prompts[0].language == "zh_hant"
    assert items[0].prompts[0].is_original is True
    assert items[0].prompts[0].provenance["kind"] == "source"
    detail = ItemRepository(tmp_path / "library").get_item(items[0].id)
    assert detail is not None
    assert "CC BY 4.0" in (detail.notes or "")
    assert "Original source URL" not in (detail.notes or "")
    assert "Original source file" not in (detail.notes or "")
    assert len(detail.notes or "") < 180


def test_install_sample_data_script_verifies_release_zip_checksum():
    installer = (ROOT / "scripts" / "install-sample-data.sh").read_text()

    assert "EXPECTED_SHA256" in installer
    assert "zipfile.ZipFile" in installer
    assert "unzip" not in installer
    assert "sha256sum" in installer or "shasum -a 256" in installer
    assert "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035" in installer


def test_install_sample_data_script_supports_local_zip_override_without_system_unzip(tmp_path: Path):
    tool_bin = tmp_path / "tool-bin"
    tool_bin.mkdir()
    for command in ("dirname", "rm", "mkdir"):
        command_path = shutil.which(command)
        assert command_path, f"{command} should be available in the test environment"
        (tool_bin / command).symlink_to(command_path)

    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), "blue").save(image_dir / "fixture.png")
    manifest = tmp_path / "fixture-manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 2,
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
            "prompts": [{
                "language": "en",
                "text": "A blue square",
                "is_primary": True,
                "is_original": True,
                "provenance": {"kind": "source", "source_language": "en", "derived_from": None, "method": None},
            }],
        }],
    }), encoding="utf-8")
    zip_path = tmp_path / "sample-images.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(image_dir / "fixture.png", "images/fixture.png")

    library = tmp_path / "library"
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "install-sample-data.sh"), "en"],
        cwd=ROOT,
        env={
            "PATH": str(tool_bin),
            "IMAGE_PROMPT_LIBRARY_PATH": str(library),
            "PYTHON": sys.executable,
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
        },
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Imported 1 items" in result.stdout
    assert ItemRepository(library).list_items(limit=5).total == 1
