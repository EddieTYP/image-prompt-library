from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_item_save_refreshes_visible_item_query():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    assert "const [itemsReloadKey, setItemsReloadKey]" in app
    assert "useItemsQuery(debouncedQ, clusterId, undefined, 1000, itemsReloadKey)" in app
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


def test_topbar_uses_attached_header_logo_branding():
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    logo_asset = ROOT / "frontend" / "src" / "assets" / "header-logo.png"
    assert "../assets/header-logo.png" in topbar
    assert "className=\"logo-mark\"" in topbar
    assert "alt=\"\"" in topbar
    assert "Image Prompt Library" in topbar
    assert "<b>Prompt Library</b>" not in topbar
    assert "ChatGPT Image2 reference" not in topbar
    assert "Sparkles" not in topbar
    assert logo_asset.exists()
    # Edward explicitly asked to use the latest attached logo image, not a cropped/optimized derivative.
    assert logo_asset.stat().st_size > 80_000
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is available in the project test env.
        Image = None
    if Image is not None:
        with Image.open(logo_asset) as img:
            assert img.size == (578, 578)
            assert img.mode == "RGBA"
            assert img.getchannel("A").getextrema()[0] == 0
    compact_css = css.replace(" ", "")
    assert ".logo{display:flex;align-items:center;gap:12px;padding:0;background:transparent;border:0;box-shadow:none;white-space:nowrap}" in compact_css
    assert ".logo-mark" in css
    assert "width:64px" in css
    assert "height:64px" in css


def test_explore_is_thumbnail_constellation_with_configurable_budgets():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "thumbnail-constellation" in explore
    assert "constellation-canvas" in explore
    assert "constellation-cluster-card" in explore
    assert "constellation-thumb-card" in explore
    assert "GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY" in app
    assert "FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY" in app
    assert "globalThumbnailBudget" in app and "focusThumbnailBudget" in app
    assert "Global thumbnail budget" in config
    assert "Focus thumbnail budget" in config
    assert "allocateGlobalThumbnailBudget" in explore
    assert "minimumAllocation" in explore
    assert ".thumbnail-constellation" in css
    assert ".constellation-thumb-card" in css
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
    assert "constellation-focus-panel" in explore
    assert ".constellation-focus-panel" in css
    assert "centerFocusedCluster" in explore


def test_explore_uses_real_thumbnails_not_dots_or_originals():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "function getConstellationImagePath" in explore
    assert "first_image?.thumb_path || item.first_image?.preview_path" in explore
    assert "first_image?.original_path" not in explore
    assert "lod-dot" not in explore
    assert "node-placeholder" not in explore
    assert "loading=\"lazy\"" in explore
    assert "decoding=\"async\"" in explore
    assert ".orbit-node.lod-dot" not in css


def test_global_explore_fits_viewport_and_cards_remain_scrollable():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "className={`app ${view === 'explore' ? 'explore-mode' : 'cards-mode'}`}" in app
    assert "<main className=\"app-main\">" in app
    assert ".app.explore-mode{height:100vh;overflow:hidden;display:flex;flex-direction:column}" in compact_css
    assert ".app.explore-mode .app-main{flex:1;min-height:0;width:100%;padding:" in css
    assert ".app.explore-mode .thumbnail-constellation{height:100%;min-height:0}" in css
    assert ".app.cards-mode" not in css
    assert "main{max-width:1680px;margin:0auto;padding:26px30px88px}" in compact_css


def test_explore_has_lightweight_hover_preview_without_layout_mutation():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "'--node-rotation': `${node.rotation}deg`" in explore
    assert "transform: `translate(-50%, -50%) rotate(${node.rotation}deg)`" not in explore
    assert "transform:translate(-50%,-50%)rotate(var(--node-rotation,0deg))" in compact_css
    assert "@media(hover:hover)and(pointer:fine)" in compact_css
    assert ".thumbnail-constellation .constellation-thumb-card:hover" in css
    assert ".thumbnail-constellation .constellation-thumb-card:focus-visible" in css
    assert ".thumbnail-constellation:not(.is-focused) .constellation-thumb-card:hover" not in css
    assert "scale(1.42)" in css
    assert "will-change:transform" in css
    assert "width:" not in css.split("@media (hover: hover) and (pointer: fine)", 1)[-1].split("}", 1)[0]
    assert "height:" not in css.split("@media (hover: hover) and (pointer: fine)", 1)[-1].split("}", 1)[0]


def test_explore_has_static_repulsive_relaxation_and_tap_drag_threshold():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    assert "TAP_DRAG_THRESHOLD" in explore
    assert "tapTarget" in explore
    assert "dragged:" in explore
    assert "Math.hypot" in explore
    assert "settleCollisionAwarePositions" in explore
    assert "doesCollide" in explore
    assert "spiralStep" in explore
    assert "relaxConstellationNodes" in explore
    assert "RELAXATION_ITERATIONS = 120" in explore
    assert "REPULSION_STRENGTH = 0.42" in explore
    assert "CLUSTER_REPULSION_STRENGTH = 0.52" in explore
    assert "SPRING_STRENGTH = 0.025" in explore
    assert "const collisionPadding = 18" in explore
    assert "const baseRadius = focused ? 220 : 146" in explore
    assert "const radiusStep = focused ? 23 : 14" in explore
    assert "repelAgainstClusterHubs" in explore
    assert "clampRelaxedNode" in explore
    assert "GLOBAL_THUMB_WIDTH = 88" in explore
    assert "GLOBAL_THUMB_HEIGHT = 112" in explore
    assert "buildCompactFocusSlots" in explore
    assert "FOCUS_SLOT_GAP = 16" in explore
    assert "slotStepX" in explore and "slotStepY" in explore
    assert "Math.hypot((x - pos.x) * 0.78, (y - pos.y) * 1.35)" in explore
    assert "rotation: 0" in explore
    assert "displayedClusters = focusedClusterId ? constellation.filter(cluster => !cluster.inactive) : constellation" in explore
    assert "resolveConstellationNodeOverlaps" in explore
    assert "placeWithoutGlobalOverlap" in explore
    assert "attempt <= 1800" in explore
    assert "'--node-rotation': `${node.rotation}deg`" in explore
    assert "continuous physics" not in explore.lower()


def test_empty_library_states_have_inline_first_prompt_cta():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "openNewItemEditor" in app
    assert "onAdd={openNewItemEditor}" in app
    assert "Your library is empty" in explore
    assert "Add your first prompt" in explore
    assert "onAdd" in explore
    assert "Add your first prompt" in cards
    assert "onAdd" in cards
    assert "empty-actions" in css


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


def test_cards_reserve_image_aspect_ratio_before_lazy_decode():
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "imageAspectRatio" in card
    assert "item.first_image?.width" in card
    assert "item.first_image?.height" in card
    assert "aspectRatio: imageAspectRatio" in card
    assert "card-image-frame" in card
    assert "has-reserved-ratio" in card
    assert "natural-ratio" in card
    assert "width={item.first_image?.width || undefined}" in card
    assert "height={item.first_image?.height || undefined}" in card
    assert ".card-image-frame" in css
    assert "aspect-ratio:var(--card-image-ratio" in css.replace(" ", "")
    assert ".card-image-frame img" in css
    assert "height:100%" in css


def test_copy_prompt_uses_shared_preferred_language_resolver():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    utils = (ROOT / "frontend" / "src" / "utils" / "prompts.ts").read_text()
    clipboard = (ROOT / "frontend" / "src" / "utils" / "clipboard.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "PromptLanguage" in utils
    assert "resolvePromptText" in utils
    assert "copyTextToClipboard" in clipboard
    assert "preferredLanguage" in app
    assert "preferred_prompt_language" in app
    assert "zh_hant" in config and "zh_hans" in config and "en" in config
    assert "onCopyPrompt" in card and "prompt_snippet || item.title" not in card
    assert "toast" in app
    assert "showCopyToast" in app
    assert "Prompt copied" in app
    assert "Copy failed" in app
    assert "toast copy-toast elegant-toast" in app
    assert "toast-icon" in app and "toast-title" in app
    assert ".elegant-toast" in css
    assert "backdrop-filter:blur" in css
    assert "@keyframes toast-in" in css
    assert "resolvePromptText" in detail
    assert "preferredLanguage" in detail
    assert "const copyText = prompt?.text || resolvePromptText" in detail
    assert "onCopyPrompt" in detail
    assert "copyTextToClipboard(copyText)" in detail
    assert "setCopyFeedback" not in detail


def test_detail_modal_dedupes_image_rail_and_hides_single_image_rail():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    assert "uniqueImages" in detail
    assert "getImageIdentity" in detail
    assert "seenImageKeys" in detail
    assert "primaryImage = uniqueImages[0]" in detail
    assert "uniqueImages.length > 1" in detail
    assert "uniqueImages.map" in detail
    assert "item.images.map" not in detail


def test_filters_and_explore_budget_controls_match_vista_style():
    filters = (ROOT / "frontend" / "src" / "components" / "FiltersPanel.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "filter-drawer" in filters
    assert "filter-search" in filters
    assert "filter-pill-grid" in filters
    assert "Collections" in filters
    assert "All references" in filters
    assert "collectionQuery" in filters
    assert "filteredClusters" in filters
    assert "No collections found" in filters
    assert "Use clusters as quick filter chips" not in filters
    assert "Templates</h2>" not in filters
    assert "onClear" in filters and "clearCluster" in app
    assert "handleFilterSelect" in app
    assert "view === 'explore' ? focusCluster(c) : selectCluster(c)" in app
    assert "type=\"range\"" in config
    assert "range-setting" in config
    assert "range-ticks" in config
    assert "GLOBAL_BUDGET_MIN = 50" in config
    assert "GLOBAL_BUDGET_MAX = 150" in config
    assert "FOCUS_BUDGET_MIN = 24" in config
    assert "FOCUS_BUDGET_MAX = 100" in config
    assert ".filter-drawer" in css
    assert ".filter-pill-grid" in css
    assert ".filter-empty" in css
    assert ".range-setting" in css
    assert ".range-ticks" in css


def test_drawer_close_buttons_use_shared_polished_panel_close_style():
    filters = (ROOT / "frontend" / "src" / "components" / "FiltersPanel.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "className=\"panel-close\"" in filters
    assert "className=\"panel-close\"" in config
    assert ".panel-close" in css
    assert "width:38px" in css
    assert "border-radius:999px" in css
    assert "aria-label=\"Close filters\"" in filters
    assert "aria-label=\"Close config\"" in config


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


def test_editor_supports_multilingual_prompts_collection_suggestions_and_image_requirements():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()

    assert "clusters={clusters}" in app
    assert "tags={tags}" in app
    assert "clusters: ClusterRecord[]" in editor
    assert "tags: TagRecord[]" in editor
    assert "initialTraditionalPrompt" in editor
    assert "promptText(item, 'zh_hant') || promptText(item, 'original')" in editor
    assert "zhHantPrompt" in editor and "zhHansPrompt" in editor and "englishPrompt" in editor
    assert "language: 'zh_hant'" in editor
    assert "language: 'zh_hans'" in editor
    assert "language: 'en'" in editor
    assert "Traditional Chinese prompt" in editor
    assert "Simplified Chinese prompt" in editor
    assert "English prompt" in editor
    assert "collection-suggestions" in editor
    assert "filteredClusters" in editor
    assert "list=\"collection-suggestions\"" in editor
    assert "tag-suggestions" in editor
    assert "filteredTags" in editor
    assert "list=\"tag-suggestions\"" in editor
    assert "Original" not in detail
    assert "'original'" not in detail
    assert "Result image" in editor and "required" in editor
    assert "Reference photo" in editor and "optional" in editor
    assert "resultFile" in editor and "referenceFile" in editor
    assert "hasExistingResultImage" in editor
    assert "missingRequiredImage" in editor
    assert "result_image" in types
    assert "reference_image" in types
    assert "role?: UploadImageRole" in types
    assert "fd.set('role', role)" in api_client


def test_delete_action_archives_item_and_refreshes_visible_data():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()

    assert "deleteItem" in api_client
    assert "method: 'DELETE'" in api_client
    assert "onDeleted" in app
    assert "setItemsReloadKey(k => k + 1)" in app
    assert "Delete reference" in editor
    assert "confirm('Delete this reference?" in editor
    assert "api.deleteItem(item.id)" in editor
    assert "danger" in editor
