import json
import runpy
from pathlib import Path

from PIL import Image

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
    assert "VITE_DEMO_MODE=true" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/" in package_json


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


def test_demo_export_only_includes_tags_from_public_items(tmp_path):
    library = tmp_path / "library"
    originals = library / "originals"
    originals.mkdir(parents=True)
    Image.new("RGB", (18, 12), "blue").save(originals / "public.png")
    Image.new("RGB", (18, 12), "red").save(originals / "private.png")
    repo = ItemRepository(library)
    public_item = repo.create_item(ItemCreate(
        title="Public item",
        source_name="wuyoscar/gpt_image_2_skill",
        tags=["public-only", "shared"],
        prompts=[PromptIn(language="en", text="Public prompt", is_original=True)],
    ))
    private_item = repo.create_item(ItemCreate(
        title="Private item",
        source_name="personal-library",
        tags=["private-only", "shared"],
        prompts=[PromptIn(language="en", text="Private prompt", is_original=True)],
    ))
    repo.add_image(public_item.id, StoredImageInput(original_path="originals/public.png"))
    repo.add_image(private_item.id, StoredImageInput(original_path="originals/private.png"))
    (library / "auth.json").write_text("demo-auth-canary", encoding="utf-8")
    (library / "config.json").write_text("demo-config-canary", encoding="utf-8")
    output = tmp_path / "demo-output"
    export_demo = runpy.run_path(str(ROOT / "scripts" / "export-demo-data.py"))["export_demo"]

    export_demo(library, output)

    tags = json.loads((output / "tags.json").read_text(encoding="utf-8"))
    assert {tag["name"] for tag in tags} == {"public-only", "shared"}
    assert next(tag for tag in tags if tag["name"] == "shared")["count"] == 1
    output_bytes = b"".join(path.read_bytes() for path in output.rglob("*") if path.is_file())
    assert b"demo-auth-canary" not in output_bytes
    assert b"demo-config-canary" not in output_bytes


def test_committed_demo_json_excludes_private_runtime_fields():
    demo_root = ROOT / "frontend" / "public" / "demo-data"

    for path in demo_root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert PRIVATE_RUNTIME_KEYS.isdisjoint(nested_keys(payload)), path
