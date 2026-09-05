import json
import hashlib
import runpy
import zipfile
from pathlib import Path

from PIL import Image
import pytest

from backend.db import connect
from backend.repositories import ItemRepository, StoredImageInput
from backend.schemas import ItemCreate, PromptIn


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_RUNTIME_KEYS = {
    "tokens",
    "access_token",
    "refresh_token",
    "id_token",
    "auth_mode",
    "auth_store_path",
    "account_id",
    "token_present",
    "providers",
    "client_id",
    "device_auth_id",
    "user_code",
    "authorization_code",
    "code_verifier",
    "session_id",
}


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def test_github_pages_demo_mode_uses_static_data_and_base_path():
    vite_config = (ROOT / "vite.config.ts").read_text()
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    package_json = (ROOT / "package.json").read_text()

    assert "VITE_BASE_PATH" in vite_config
    assert "base:" in vite_config
    assert "VITE_DEMO_MODE" in client
    assert "DEMO_DATA_BASE" in client
    assert "demo-data/items.json" in client
    assert "demo-data/clusters.json" in client
    assert "demo-data/tags.json" in client
    assert '"build:demo"' in package_json
    assert "vite build --mode demo --base /image-prompt-library/" in package_json
    assert "VITE_DEMO_MODE=true" in (ROOT / "frontend" / ".env.demo").read_text(encoding="utf-8")


def test_github_pages_demo_banner_uses_versionless_local_install_highlights():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    translations = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text(encoding="utf-8")

    assert "t('localInstallHighlights')" in app
    assert "multi-image generation, and complete backup and restore" in translations
    assert "多張生成及完整備份與還原" in translations
    assert "localV06SupportsMobileGeneration" not in translations
    assert "Latest v0.7" not in translations
    assert "最新 v0.7" not in translations
    assert "最新 v0.6" not in translations


def test_github_pages_workflow_deploys_current_demo_with_legacy_redirects():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text()

    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in workflow
    assert "actions/checkout@v5" in workflow
    assert "actions/configure-pages@v6" in workflow
    assert "actions/upload-pages-artifact@v5" in workflow
    assert "actions/deploy-pages@v5" in workflow
    assert "npm ci" in workflow
    assert "npm run build:demo" in workflow
    assert "Preserve published version routes" in workflow
    assert "for route in v0.1 v0.2 v0.3 v0.4 v0.6 v0.7" in workflow
    assert 'url=/image-prompt-library/' in workflow
    assert 'frontend/dist/$route/index.html' in workflow
    assert "path: frontend/dist" in workflow
    assert "git worktree" not in workflow
    assert "ARCHIVED_" not in workflow
    assert ".pages-artifact" not in workflow


def test_demo_export_script_outputs_compact_static_assets():
    script = (ROOT / "scripts" / "export-demo-data.py").read_text()

    assert "frontend/public/demo-data" in script
    assert "DEMO_IMAGE_MAX_WIDTH" in script
    assert "DEMO_IMAGE_QUALITY" in script
    assert "items.json" in script
    assert "clusters.json" in script
    assert "tags.json" in script
    assert "PUBLIC_DEMO_SOURCES" in script


def test_demo_data_bundle_is_present_and_uses_compressed_media_paths():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text(encoding="utf-8")
    clusters = json.loads((demo_root / "clusters.json").read_text(encoding="utf-8"))
    items = json.loads(items_text)
    sources = {item.get("source_name") for item in items}

    assert (demo_root / "tags.json").exists()
    assert len(items) == 533
    assert {"wuyoscar/gpt_image_2_skill", "freestylefly/awesome-gpt-image-2"} <= sources
    assert all(
        {prompt.get("language") for prompt in item.get("prompts", [])} >= {"zh_hant", "zh_hans"}
        for item in items
    )
    assert not any("http" in str(item.get("author", "")) for item in items)
    assert "demo-data/media/" in items_text
    assert ".webp" in items_text
    assert "originals/" not in items_text
    assert "library/db.sqlite" not in items_text
    assert clusters and all(cluster.get("names", {}).get("zh_hant") for cluster in clusters)
    items_by_id = {item["id"]: item for item in items}
    for cluster in clusters:
        preview_ids = cluster.get("preview_item_ids", [])
        preview_paths = cluster.get("preview_images", [])
        assert len(preview_ids) == len(preview_paths)
        for item_id, preview_path in zip(preview_ids, preview_paths, strict=True):
            item = items_by_id[item_id]
            assert item.get("cluster", {}).get("id") == cluster["id"]
            assert item.get("first_image", {}).get("thumb_path") == preview_path


def test_demo_export_only_includes_tags_from_public_items(tmp_path):
    library = tmp_path / "library"
    originals = library / "originals"
    originals.mkdir(parents=True)
    Image.new("RGB", (18, 12), "blue").save(originals / "public.png")
    Image.new("RGB", (18, 12), "red").save(originals / "private.png")
    repo = ItemRepository(library)
    public_item = repo.create_item(ItemCreate(
        title="Public item",
        cluster_name="Public collection",
        source_name="wuyoscar/gpt_image_2_skill",
        tags=["public-only", "shared"],
        prompts=[PromptIn(language="en", text="Render UI label access_token=example", is_original=True)],
    ))
    private_item = repo.create_item(ItemCreate(
        title="Private item",
        cluster_name="Private collection",
        source_name="personal-library",
        tags=["private-only", "shared"],
        prompts=[PromptIn(language="en", text="Private prompt", is_original=True)],
    ))
    repo.add_image(public_item.id, StoredImageInput(original_path="originals/public.png"))
    repo.add_image(private_item.id, StoredImageInput(original_path="originals/private.png"))
    with connect(library) as connection:
        connection.execute(
            "UPDATE prompts SET provenance=? WHERE item_id=?",
            (
                json.dumps({
                    "kind": "manual",
                    "note": "access_token=demo-provenance-canary",
                    "authMode": "private-runtime-mode",
                    "accountId": "private-account-canary",
                }),
                public_item.id,
            ),
        )
        connection.commit()
    (library / "auth.json").write_text("demo-auth-canary", encoding="utf-8")
    (library / "config.json").write_text("demo-config-canary", encoding="utf-8")
    output = tmp_path / "demo-output"
    export_demo = runpy.run_path(str(ROOT / "scripts" / "export-demo-data.py"))["_write_demo"]

    export_demo(library, output)

    tags = json.loads((output / "tags.json").read_text(encoding="utf-8"))
    clusters = json.loads((output / "clusters.json").read_text(encoding="utf-8"))
    assert {tag["name"] for tag in tags} == {"public-only", "shared"}
    assert next(tag for tag in tags if tag["name"] == "shared")["count"] == 1
    assert [cluster["name"] for cluster in clusters] == ["Public collection"]
    assert clusters[0]["preview_item_ids"] == [json.loads((output / "items.json").read_text(encoding="utf-8"))[0]["id"]]
    output_bytes = b"".join(path.read_bytes() for path in output.rglob("*") if path.is_file())
    assert b"demo-auth-canary" not in output_bytes
    assert b"demo-config-canary" not in output_bytes
    assert b"demo-provenance-canary" not in output_bytes
    assert b"private-account-canary" not in output_bytes
    exported_items = json.loads((output / "items.json").read_text(encoding="utf-8"))
    assert exported_items[0]["prompts"][0]["text"] == "Render UI label access_token=example"
    exported_provenance = exported_items[0]["prompts"][0]["provenance"]
    assert exported_provenance["note"] == "[redacted credential data]"
    assert "authMode" not in exported_provenance
    assert "accountId" not in exported_provenance


def test_committed_demo_json_excludes_private_runtime_fields():
    demo_root = ROOT / "frontend" / "public" / "demo-data"

    for path in demo_root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert PRIVATE_RUNTIME_KEYS.isdisjoint(nested_keys(payload)), path


def demo_packages(tmp_path, monkeypatch):
    module = runpy.run_path(str(ROOT / "scripts" / "export-demo-data.py"))
    export = module["export_demo"]
    image = tmp_path / "public.png"
    Image.new("RGB", (18, 12), "blue").save(image)
    archives, packages = [], []
    for index in range(2):
        manifest = tmp_path / f"manifest-{index}.json"
        manifest.write_text(json.dumps({
            "schema_version": 2, "id": f"public-{index}", "language": "en",
            "source": {"name": "wuyoscar/gpt_image_2_skill"},
            "collections": [{"id": "public", "name": "Public collection"}],
            "items": [{"id": f"public-{index}", "title": f"Public {index}",
                       "image": "public.png", "collection_id": "public", "tags": ["public-tag"],
                       "prompts": [{"language": "en", "text": "Public prompt"}]}],
        }), encoding="utf-8")
        archive = tmp_path / f"images-{index}.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.write(image, "public.png")
        archives.append(archive)
        packages.append((manifest, hashlib.sha256(archive.read_bytes()).hexdigest()))
    monkeypatch.setitem(export.__globals__, "SAMPLE_PACKAGES", tuple(packages))
    return export, archives


def test_demo_export_rebuilds_samples_without_reading_edited_library(tmp_path, monkeypatch):
    export, archives = demo_packages(tmp_path, monkeypatch)
    private_library = tmp_path / "private-library"
    repo = ItemRepository(private_library)
    item = repo.create_item(ItemCreate(
        title="PRIVATE TITLE", slug="public-0", source_name="wuyoscar/gpt_image_2_skill",
        notes="PRIVATE NOTES", tags=["PRIVATE TAG"],
        prompts=[PromptIn(language="en", text="PRIVATE PROMPT", is_original=True)],
    ))
    original = private_library / "originals" / "private.png"
    original.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (30, 30), "red").save(original)
    repo.add_image(item.id, StoredImageInput(original_path="originals/private.png"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_PATH", str(private_library))
    output = tmp_path / "output"

    export(*archives, output)

    items = json.loads((output / "items.json").read_text(encoding="utf-8"))
    assert len(items) == 2
    assert {item["title"] for item in items} == {"Public 0", "Public 1"}
    assert all(len(item["images"]) == 1 for item in items)
    assert b"PRIVATE" not in b"".join(path.read_bytes() for path in output.glob("*.json"))
    assert repo.get_item(item.id).notes == "PRIVATE NOTES"
    for image in (output / "media").glob("*.webp"):
        with Image.open(image) as decoded:
            assert decoded.size == (18, 12)


@pytest.mark.parametrize("changed_index", [0, 1])
def test_demo_export_rejects_modified_archives_before_replacing_output(tmp_path, monkeypatch, changed_index):
    export, archives = demo_packages(tmp_path, monkeypatch)
    with zipfile.ZipFile(archives[changed_index], "a") as bundle:
        bundle.writestr("private-note.txt", "PRIVATE NOTES")
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "items.json"
    sentinel.write_text("existing demo", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        export(*archives, output)
    assert sentinel.read_text(encoding="utf-8") == "existing demo"


def test_demo_exports_are_byte_identical_across_fresh_imports(tmp_path, monkeypatch):
    import backend.repositories as repositories
    import backend.services.import_sample_bundle as importer

    export, archives = demo_packages(tmp_path, monkeypatch)
    outputs = [tmp_path / "first", tmp_path / "second"]
    for index, output in enumerate(outputs):
        timestamp = f"202{index}-01-01T00:00:00+00:00"
        monkeypatch.setattr(repositories, "now", lambda: timestamp)
        monkeypatch.setattr(importer, "now", lambda: timestamp)
        export(*archives, output)
    snapshots = [{p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()} for output in outputs]
    assert snapshots[0] == snapshots[1]
    items = json.loads(snapshots[0]["items.json"])
    for item in items:
        assert all(record["item_id"] == item["id"] for record in item["images"] + item["prompts"])
        assert item["first_image"] == item["images"][0]
