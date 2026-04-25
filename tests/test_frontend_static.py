from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_item_save_refreshes_visible_item_query():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    assert "const [itemsReloadKey, setItemsReloadKey]" in app
    assert "useItemsQuery(debouncedQ, clusterId, undefined, 300, itemsReloadKey)" in app
    assert "setItemsReloadKey(k => k + 1)" in app
    assert "reloadKey" in hook
    assert "[q, clusterId, tag, viewLimit, reloadKey]" in hook


def test_topbar_is_toolbar_search_not_hero_or_keyboard_shortcut():
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    assert "toolbar-search" in topbar
    assert "active-filter-strip" in topbar
    assert "view-dock" in topbar
    assert "hero-shell" not in topbar
    assert "Start your visual prompt collection" not in topbar
    assert "Keyboard shortcut" not in topbar
    assert "⌘K" not in topbar and "Ctrl+K" not in topbar
    assert "metaKey" not in app and "ctrlKey" not in app


def test_explore_is_spatial_orbit_map_with_cluster_caps():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "spatial-orbit-map" in explore
    assert "orbit-canvas" in explore
    assert "orbit-cluster-label" in explore
    assert "orbit-node" in explore
    assert "MAX_VISIBLE_NODES_PER_CLUSTER" in explore
    assert "FOCUSED_VISIBLE_NODES_PER_CLUSTER" in explore
    assert "favorite" in explore
    assert "+{cluster.hiddenCount} more" in explore
    assert ".spatial-orbit-map" in css
    assert ".cluster-orbit{" not in css


def test_cards_keep_adaptive_masonry_and_actions():
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "masonry-like" in cards
    assert "breakInside" in card
    assert "Copy prompt" in card
    assert "Favorite" in card
    assert "Edit" in card
    assert "onFavorite" in card and "onEdit" in card
    assert "column-width:var(--card-min)" in css.replace(" ", "")
    assert "break-inside:avoid" in css.replace(" ", "")


def test_copy_prompt_uses_shared_preferred_language_resolver():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    utils = (ROOT / "frontend" / "src" / "utils" / "prompts.ts").read_text()
    assert "PromptLanguage" in utils
    assert "resolvePromptText" in utils
    assert "preferredLanguage" in app
    assert "preferred_prompt_language" in app
    assert "zh_hant" in config and "zh_hans" in config and "en" in config
    assert "onCopyPrompt" in card and "prompt_snippet || item.title" not in card
    assert "resolvePromptText" in detail
    assert "preferredLanguage" in detail
    assert "const copyText = prompt?.text || resolvePromptText" in detail
    assert "navigator.clipboard?.writeText(copyText)" in detail


def test_gallery_visuals_are_polished():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "modal-hero" in detail and "prompt-panel" in detail
    assert "editor-grid" in editor and "drop-zone" in editor
    assert "--surface-warm" in css
    assert ".fab{position:fixed;right:32px;bottom:32px" in css.replace("\n", "")
