from pathlib import Path
import json

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
    assert "mediaUrl = (path?: string)" in client
    assert "demoUrl" in client
    assert '"build:demo"' in package_json
    assert "VITE_DEMO_MODE=true" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/" in package_json


def test_github_pages_demo_is_read_only_and_discloses_compressed_images():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "isDemoMode" in app
    assert "demo-banner" in app
    assert "onlineReadOnlyDemo" in i18n
    assert "readOnlySampleLibrary" not in i18n
    assert "compressedForDemo" in i18n
    assert "runLocallyForPrivateLibrary" in i18n
    assert "localV06SupportsMobileGeneration" in i18n
    assert "Online Read Only Demo" in i18n
    assert "Demo 圖片已壓縮。" in i18n
    assert "新增／編輯需要本機安裝，請在本機運行以建立你的私人 prompt library。" in i18n
    assert "最新 v0.6 beta 改善本機生成流程與流動裝置體驗" in i18n
    assert "showActions" in cards
    assert "showMutations" in detail
    assert "!isDemoMode && <button className=\"fab\"" in app
    assert "onAdd={isDemoMode ? undefined : openNewItemEditor}" in app
    assert "onFavorite={isDemoMode ? undefined : favorite}" in app
    assert "onEdit={isDemoMode ? undefined : editSummary}" in app


def test_github_pages_workflow_deploys_versioned_demo_builds():
    workflow = ROOT / ".github" / "workflows" / "pages.yml"
    assert workflow.exists()
    text = workflow.read_text()
    assert "actions/configure-pages" in text
    assert "actions/upload-pages-artifact" in text
    assert "actions/deploy-pages" in text
    assert "fetch-depth: 0" in text
    assert "LEGACY_DEMO_REF: v0.1.0-alpha" in text
    assert "CURRENT_PREVIEW_PATH: v0.6" in text
    assert "ARCHIVED_03_DEMO_REF: v0.3.0-alpha" in text
    assert "ARCHIVED_03_DEMO_PATH: v0.3" in text
    assert "ARCHIVED_02_DEMO_REF: v0.2.0-alpha" in text
    assert "ARCHIVED_02_DEMO_PATH: v0.2" in text
    assert "VITE_BASE_PATH=/image-prompt-library/${CURRENT_PREVIEW_PATH}/ npm run build" in text
    assert "VITE_BASE_PATH=/image-prompt-library/${ARCHIVED_03_DEMO_PATH}/ npm run build" in text
    assert "git worktree add .page-build/${ARCHIVED_03_DEMO_PATH} ${ARCHIVED_03_DEMO_REF}" in text
    assert "VITE_BASE_PATH=/image-prompt-library/${ARCHIVED_02_DEMO_PATH}/ npm run build" in text
    assert "git worktree add .page-build/${LEGACY_DEMO_PATH} ${LEGACY_DEMO_REF}" in text
    assert "VITE_BASE_PATH=/image-prompt-library/${LEGACY_DEMO_PATH}/ npm run build" in text
    assert ".pages-artifact/${CURRENT_PREVIEW_PATH}" in text
    assert ".pages-artifact/${ARCHIVED_03_DEMO_PATH}" in text
    assert ".pages-artifact/${ARCHIVED_02_DEMO_PATH}" in text
    assert ".pages-artifact/${LEGACY_DEMO_PATH}" in text
    assert "Online Read Only Demo" in text
    assert "Demo images are compressed." in text
    assert "Add/edit require local install; run locally to create your private prompt library." in text
    assert "Latest v0.6 beta improves the mobile generation workflow" in text
    assert "local-generation-studio-banner.webp" in text
    assert "hero-banner" in text
    assert "View the v0.6 beta Generation Workflow & Mobile Polish release" in text
    assert "cp docs/assets/screenshots/local-generation-studio-banner.webp" in text
    assert "View on GitHub" in text
    assert "Inject v0.4 upgrade notice into archived v0.3 preview" in text
    assert "This v0.3 preview is archived." in text
    assert "Go to the latest v0.4 demo" in text
    assert "localStorage.getItem('image-prompt-library-hide-v03-upgrade')" in text
    assert "Multilingual provenance-aware prompt vault" in text
    assert "Archived 0.2 preview" in text
    assert "Original alpha demo" in text
    assert "path: .pages-artifact" in text


def test_package_exposes_versioned_demo_build_scripts():
    package_json = (ROOT / "package.json").read_text()
    assert '"build:demo:v0.1"' in package_json
    assert '"build:demo:v0.2"' in package_json
    assert '"build:demo:v0.3"' in package_json
    assert '"build:demo:v0.4"' in package_json
    assert '"build:demo:v0.6"' in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.1/" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.2/" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.3/" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.4/" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.6/" in package_json


def test_demo_export_script_outputs_compact_static_assets():
    script = ROOT / "scripts" / "export-demo-data.py"
    assert script.exists()
    text = script.read_text()
    assert "frontend/public/demo-data" in text
    assert "DEMO_IMAGE_MAX_WIDTH" in text
    assert "DEMO_IMAGE_QUALITY" in text
    assert "compressed" in text.lower()
    assert "items.json" in text
    assert "clusters.json" in text
    assert "tags.json" in text


def test_demo_data_bundle_is_present_and_uses_compressed_media_paths():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    assert (demo_root / "items.json").exists()
    assert (demo_root / "clusters.json").exists()
    assert (demo_root / "tags.json").exists()
    items_text = (demo_root / "items.json").read_text()
    clusters = json.loads((demo_root / "clusters.json").read_text(encoding="utf-8"))
    items = json.loads(items_text)
    sources = {item.get("source_name") for item in items}
    assert len(items) == 510
    assert {"wuyoscar/gpt_image_2_skill", "freestylefly/awesome-gpt-image-2"} <= sources
    assert all({prompt.get("language") for prompt in item.get("prompts", [])} >= {"en", "zh_hant", "zh_hans"} for item in items)
    assert not any("http" in str(item.get("author", "")) for item in items)
    assert not any("[" in str(item.get("author", "")) and "](" in str(item.get("author", "")) for item in items)
    assert "demo-data/media/" in items_text
    assert ".webp" in items_text
    assert "originals/" not in items_text
    assert "library/db.sqlite" not in items_text
    assert clusters and all(cluster.get("names", {}).get("zh_hant") for cluster in clusters)
    assert items and all(item.get("cluster", {}).get("names", {}).get("zh_hant") for item in items if item.get("cluster"))
