from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_item_save_refreshes_visible_item_query():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    assert "const [itemsReloadKey, setItemsReloadKey]" in app
    assert "useItemsQuery(debouncedQ, clusterId, undefined, 100, itemsReloadKey)" in app
    assert "setItemsReloadKey(k => k + 1)" in app
    assert "reloadKey" in hook
    assert "[q, clusterId, tag, viewLimit, reloadKey]" in hook


def test_explore_preview_images_have_unique_react_keys():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    assert "(p, idx)" in explore
    assert "key={`${c.id}-${idx}-${p}`}" in explore


def test_vista_inspired_home_has_hero_and_marketplace_visual_tokens():
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "hero-shell" in topbar
    assert "Start your visual prompt collection" in topbar
    assert "template-count" in topbar
    assert "--surface-warm" in css
    assert "#ede9dd" in css
    assert "masonry-like" in css
    assert ".cluster-card.featured" in css
    assert ".fab{position:fixed;right:32px;bottom:32px" in css.replace("\n", "")
