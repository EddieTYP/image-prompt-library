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


def test_explore_focus_mode_stays_in_map_and_has_cards_cta():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "const focusCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('explore')" in app
    assert "const openClusterAsCards = (c: ClusterRecord) => { setClusterId(c.id); setView('cards')" in app
    assert "onOpenClusterCards={openClusterAsCards}" in app
    assert "focusedClusterId" in explore
    assert "Open as Cards" in explore
    assert "onOpenClusterCards(cluster)" in explore
    assert "orbit-focus-panel" in explore
    assert ".orbit-focus-panel" in css


def test_explore_uses_ordered_rings_and_lod_image_paths():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "function getOrbitImagePath" in explore
    assert "lod: 'dot' | 'thumb' | 'preview'" in explore
    assert "scale < 0.54" in explore
    assert "first_image?.original_path" not in explore
    assert "ringIndex" in explore and "laneIndex" in explore
    assert "const ringGap" in explore
    assert "className={`orbit-node ${node.item.favorite ? 'favorite' : ''} lod-${node.lod}`}" in explore
    assert "node.lod !== 'dot' && node.imagePath" in explore
    assert ".orbit-node.lod-dot" in css
    assert ".orbit-node.lod-preview" in css


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
    clipboard = (ROOT / "frontend" / "src" / "utils" / "clipboard.ts").read_text()
    assert "PromptLanguage" in utils
    assert "resolvePromptText" in utils
    assert "copyTextToClipboard" in clipboard
    assert "preferredLanguage" in app
    assert "preferred_prompt_language" in app
    assert "zh_hant" in config and "zh_hans" in config and "en" in config
    assert "onCopyPrompt" in card and "prompt_snippet || item.title" not in card
    assert "resolvePromptText" in detail
    assert "preferredLanguage" in detail
    assert "const copyText = prompt?.text || resolvePromptText" in detail
    assert "copyTextToClipboard(copyText)" in detail


def test_copy_prompt_has_insecure_lan_clipboard_fallback():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    clipboard = (ROOT / "frontend" / "src" / "utils" / "clipboard.ts").read_text()
    assert "navigator.clipboard?.writeText" not in app
    assert "navigator.clipboard?.writeText" not in detail
    assert "navigator.clipboard?.writeText" in clipboard
    assert "document.execCommand('copy')" in clipboard
    assert "textarea.select()" in clipboard


def test_gallery_visuals_are_polished():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "modal-hero" in detail and "prompt-panel" in detail
    assert "editor-grid" in editor and "drop-zone" in editor
    assert "--surface-warm" in css
    assert ".fab{position:fixed;right:32px;bottom:32px" in css.replace("\n", "")
