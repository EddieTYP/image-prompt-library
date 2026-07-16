import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
