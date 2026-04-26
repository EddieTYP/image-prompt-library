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
    assert "t('globalThumbnailBudget')" in config
    assert "t('focusThumbnailBudget')" in config
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
    assert "t('cards')" in explore
    assert "onOpenClusterCards(cluster)" in explore
    assert "constellation-focus-panel" in explore
    assert ".constellation-focus-panel" in css
    assert "centerFocusedCluster" in explore


def test_explore_uses_real_thumbnails_not_dots_or_originals():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "function getConstellationImagePath" in explore
    assert "selectPrimaryImage([item.first_image])" in explore
    assert "imageThumbnailPath(primaryImage)" in explore
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
    assert "() => (focusedClusterId ? constellation.filter(cluster => !cluster.inactive) : constellation)" in explore
    assert "resolveConstellationNodeOverlaps" in explore
    assert "placeWithoutGlobalOverlap" in explore
    assert "attempt <= 1800" in explore
    assert "'--node-rotation': `${node.rotation}deg`" in explore
    assert "continuous physics" not in explore.lower()


def test_filter_refresh_keeps_stale_content_without_large_loading_flash():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "initialLoading" in hook
    assert "refreshing" in hook
    assert "setInitialLoading" in hook
    assert "setRefreshing" in hook
    assert "dataScope" in hook
    assert "setDataScope" in hook
    assert "return { data, loading, initialLoading, refreshing, error, dataScope }" in hook
    assert "const { data, loading, initialLoading, refreshing, error, dataScope }" in app
    assert "pendingExploreUnfilterClusterId" in app
    assert "exploreUnfilterFadePhase" in app
    assert "'out' | 'pre-in' | 'in' | 'idle'" in app
    assert "dataScope.clusterId === pendingExploreUnfilterClusterId" in app
    assert "setPendingExploreUnfilterClusterId(clusterId)" in app
    assert "setExploreUnfilterFadePhase('out')" in app
    assert "setExploreUnfilterFadePhase('pre-in')" in app
    assert "requestAnimationFrame(() => setExploreUnfilterFadePhase('in'))" in app
    assert "setExploreUnfilterFadePhase('idle')" in app
    assert "unfilterTransitionPhase={exploreUnfilterFadePhase}" in app
    assert "useEffect(() => {" in app and "setPendingExploreUnfilterClusterId(undefined)" in app
    assert "exploreFocusedClusterId" in app
    assert "dataScope.clusterId" in app
    assert "exploreFitRequestKey" in app
    assert "setExploreFitRequestKey" in app
    assert "clearCluster = () => {" in app
    clear_body = app.split("const clearCluster = () => {", 1)[1].split("  const saved =", 1)[0]
    assert "setExploreFitRequestKey" not in clear_body
    assert "app-main ${refreshing ? 'is-refreshing' : ''}" in app
    assert "aria-busy={refreshing}" in app
    assert "initialLoading && <div className=\"loading\">" in app
    assert "loading && <div className=\"loading\">" not in app
    assert "refresh-indicator" in app
    assert ".app-main.is-refreshing" in css
    assert ".refresh-indicator" in css


def test_constellation_card_drag_pans_viewport_and_disables_native_image_drag():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "type GestureState" in explore
    assert "panStartOffset" in explore
    assert "startGesture" in explore
    assert "moveGesture" in explore
    assert "finishGesture" in explore
    assert "setPointerCapture" in explore
    assert "setOffset({ x: gesture.panStartOffset.x +" in explore
    assert "dragging: true" in explore
    assert "draggable={false}" in explore
    assert "event.stopPropagation()" not in explore
    assert "onPointerDown={(event) => startGesture(event, { type: 'cluster', cluster })}" in explore
    assert "onPointerDown={(event) => startGesture(event, { type: 'item', item: node.item })}" in explore
    assert ".constellation-thumb-card,.constellation-thumb-card img,.constellation-cluster-card" in css
    assert "-webkit-user-drag:none" in css.replace(" ", "")
    assert "user-select:none" in css.replace(" ", "")


def test_constellation_blank_canvas_and_svg_drag_start_pan_without_stealing_card_taps():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    assert "function isBlankConstellationPointerTarget" in explore
    assert "target.closest('.constellation-thumb-card, .constellation-cluster-card, button, a, input, textarea, select')" in explore
    assert "target.closest('.constellation-canvas, .constellation-links')" in explore
    assert "if (!isBlankConstellationPointerTarget(event.target, event.currentTarget)) return;" in explore
    assert "event.target !== event.currentTarget" not in explore


def test_modal_and_explore_focus_use_reduced_motion_safe_transitions():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "FOCUS_TRANSITION_MS" in explore
    assert "setIsFocusAnimating" in explore
    assert "focus-animation" in explore
    assert "window.setTimeout" in explore
    assert "centerFocusedCluster" in explore
    assert "className={`constellation-canvas ${isFocusAnimating ? 'focus-animation' : ''}`}" in explore
    assert "viewportRef" in explore
    assert "getConstellationBounds(displayedClusters)" in explore
    assert "computeFitTransform" in explore
    assert "fitConstellationToViewport" in explore
    assert "Math.min(1.15, Math.max(0.42" in explore
    assert "useLayoutEffect" in explore
    assert "[focusedClusterId, displayedClusters, fitRequestKey]" in explore
    assert "fitRequestKey" in explore
    assert "lastFitRequestKeyRef" in explore
    assert "unfilterTransitionPhase" in explore
    assert "is-unfilter-fade-out" in explore
    assert "is-unfilter-fade-pre-in" in explore
    assert "is-unfilter-fade-in" in explore
    assert "isFocusAnimating" in explore
    assert "focusedClusterId || fitRequestKey" in explore
    assert "@keyframes modal-backdrop-in" in css
    assert "@keyframes modal-panel-in" in css
    assert "@keyframes modal-content-in" in css
    assert "modal-content-enter" in (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    assert "animation:modal-backdrop-in" in css.replace(" ", "")
    assert "animation:modal-panel-in" in css.replace(" ", "")
    assert "animation:modal-content-in" in css.replace(" ", "")
    assert ".detail.modal" in css and "min-height:min" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".constellation-canvas.focus-animation" in css
    assert ".thumbnail-constellation.is-unfilter-fade-out .constellation-canvas" in css
    assert ".thumbnail-constellation.is-unfilter-fade-in .constellation-canvas" in css
    assert "transition:opacity .14s ease" in css


def test_empty_library_states_have_inline_first_prompt_cta():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "openNewItemEditor" in app
    assert "onAdd={openNewItemEditor}" in app
    assert "t('libraryEmptyTitle')" in explore
    assert "t('addFirstPrompt')" in explore
    assert "onAdd" in explore
    assert "t('addFirstPrompt')" in cards
    assert "onAdd" in cards
    assert "empty-actions" in css


def test_cards_keep_adaptive_masonry_and_actions():
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "masonry-like" in cards
    assert "breakInside" in card
    assert "t('copyPrompt')" in card
    assert "t('favorite')" in card
    assert "t('edit')" in card
    assert "onFavorite" in card and "onEdit" in card
    assert "column-width:var(--card-min)" in css.replace(" ", "")
    assert "break-inside:avoid" in css.replace(" ", "")


def test_cards_reserve_image_aspect_ratio_before_lazy_decode():
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "imageAspectRatio" in card
    assert "primaryImage?.width" in card
    assert "primaryImage?.height" in card
    assert "aspectRatio: imageAspectRatio" in card
    assert "card-image-frame" in card
    assert "has-reserved-ratio" in card
    assert "natural-ratio" in card
    assert "width={primaryImage?.width || undefined}" in card
    assert "height={primaryImage?.height || undefined}" in card
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
    assert "copySuccess" in app
    assert "copyFailed" in app
    assert "toast copy-toast elegant-toast" in app
    assert "toast-icon" in app and "toast-title" in app
    assert ".elegant-toast" in css
    assert "backdrop-filter:blur" in css
    assert "@keyframes toast-in" in css
    assert "resolvePromptText" in detail
    assert "preferredLanguage" in detail
    assert "const copyText = prompt?.text || resolvedPrompt?.text || resolvePromptText" in detail
    assert "onCopyPrompt" in detail
    assert "copyTextToClipboard(text)" in detail
    assert "setCopyFeedback" not in detail


def test_ui_language_setting_localizes_main_chrome():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "UI_LANGUAGE_STORAGE_KEY" in app
    assert "loadUiLanguage" in app
    assert "uiLanguage" in app and "setUiLanguage" in app
    assert "onUiLanguage" in config
    assert "t('uiLanguage')" in config
    assert "t={t}" in app
    assert "t('filters')" in topbar
    assert "t('searchPlaceholder')" in topbar
    assert "t('noMatchingPrompts')" in cards
    assert "export type UiLanguage = 'zh_hant' | 'zh_hans' | 'en'" in i18n
    assert "繁體中文" in i18n and "简体中文" in i18n and "English" in i18n
    assert "搜尋所有 prompts、標題、標籤…" in i18n
    assert "Search all prompts, titles, tags…" in i18n
    assert "嘅" not in i18n and "搵" not in i18n and "吓" not in i18n and "幾多" not in i18n
    assert "Explore 全部 collection 的整體密度。" in i18n


def test_item_editor_uses_ui_language_for_long_tail_strings():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "<ItemEditorModal t={t}" in app
    assert "t: Translator" in editor
    assert "t('newReference')" in editor
    assert "t('editPromptCard')" in editor
    assert "t('title')" in editor
    assert "t('traditionalChinesePrompt')" in editor
    assert "t('resultImageRequired')" in editor
    assert "t('referencePhotoOptional')" in editor
    assert "t('deleteReference')" in editor
    assert "t('saveReference')" in editor
    assert "Delete reference" not in editor
    assert "Save reference" not in editor
    assert "香港" not in i18n
    assert "完成圖片為必填" in i18n


def test_detail_modal_dedupes_image_rail_and_hides_single_image_rail():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    assert "uniqueImages" in detail
    assert "getImageIdentity" in detail
    assert "seenImageKeys" in detail
    assert "selectPrimaryImage(uniqueImages)" in detail
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
    assert "t('allReferences')" in filters
    assert "collectionQuery" in filters
    assert "filteredClusters" in filters
    assert "t('noCollectionsFound')" in filters
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
    assert "aria-label={t('closeFilters')}" in filters
    assert "aria-label={t('closeConfig')}" in config


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
    assert "modal-hero" in detail and "prompt-block" in detail
    assert "editor-grid" in editor and "drop-zone" in editor
    assert "--surface-warm" in css
    assert ".fab{position:fixed;right:32px;bottom:32px" in css.replace("\n", "")


def test_detail_modal_supports_inline_editing_contract():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "onChanged" in detail and "onChanged={saved}" in app
    assert "detail-side-actions" in detail
    assert "detail-side-primary-actions" in detail
    assert "modal-icon-button favorite-button" in detail
    assert "modal-icon-button edit-button" in detail
    assert "modal-icon-button close" in detail
    assert detail.index("detail-side-actions") < detail.index("collection-inline-edit")
    assert "aria-label={item.favorite ? t('saved') : t('favorite')}" in detail
    assert "aria-label={t('edit')}" in detail
    assert ".modal-icon-button:hover" in css
    assert ".modal-icon-button:focus-visible" in css
    assert "InlineEditableField" in detail
    assert "InlineEditableTextArea" in detail
    assert "title-inline-edit" in detail
    assert ".title-inline-edit{display:inline-block;min-width:min(100%,260px);font-size:clamp(24px,2.8vw,38px);line-height:1.08;letter-spacing:-.045em}" in compact_css
    assert ".title-inline-editinput{font-size:inherit;line-height:inherit;letter-spacing:inherit" in compact_css
    assert "collection-inline-edit" in detail
    assert "metadata-inline-edit" in detail
    assert "prompt-inline-edit" in detail
    assert "notes-inline-edit" in detail
    assert "inline-edit-controls" in css
    assert "Check" in detail and "X" in detail
    assert "commitInlineUpdate" in detail
    assert "api.updateItem(item.id" in detail
    assert "promptDisplayOrder = ['en', 'zh_hant', 'zh_hans']" in detail
    assert "prompt-edit-icon" in detail
    assert "role=\"tablist\"" in detail
    assert "aria-selected={lang === promptLanguage}" in detail
    assert "availablePromptRecords" in detail
    assert "resolvePromptRecord" in detail
    assert "lastDefaultPromptKeyRef" in detail
    assert "const defaultPromptKey = `${id}:${preferredLanguage}`" in detail
    assert "lastDefaultPromptKeyRef.current === defaultPromptKey" in detail
    assert "lastDefaultPromptKeyRef.current = defaultPromptKey" in detail
    assert "setLang(nextPrompt.language)" in detail
    assert "const prompt = item?.prompts.find(promptRecord => promptRecord.language === lang)" in detail
    assert "const resolvedPrompt = resolvePromptRecord(availablePromptRecords, lang, preferredLanguage)" in detail
    assert "promptDisplayOrder.map(promptLanguage" in detail
    assert "const tabPrompt = item.prompts.find(prompt => prompt.language === promptLanguage)" in detail
    assert "onClick={() => { setLang(promptLanguage); cancelPromptEdit(); }}" in detail
    assert "disabled={!tabPrompt?.text.trim()}" not in detail
    assert "availablePromptRecords.map(promptOption" not in detail
    assert "<section className=\"prompt-block prompt-panel active\">" in detail
    assert "prompt-edit-controls" in detail and "prompt-edit-controls" in css
    assert "copyTextToClipboard(text)" in detail
    assert "promptRecord?.text ? <p>{promptRecord.text}</p>" not in detail
    assert "add-note-affordance\">{t('promptText')}" in detail
    assert "disabled={!prompt?.text}" in detail
    assert "handleCopyPrompt(prompt?.text || '')" in detail
    assert "add-note-affordance" in detail
    assert "t('addNote')" in detail
    assert "source-icon-link" in detail
    assert "ExternalLink" in detail
    assert "touch-action:manipulation" in css
    assert ".close:hover" not in css
    assert ".modal-icon-button.close" in css
    assert ".inline-editable:hover" in css
    assert ".prompt-block" in css
    assert "prompt-copy-icon" in css
    assert "prompt-language-tabs" in css
    assert "background:#fff" in css
    assert "background:#e8e2d5" in css
    assert "top:-6px" in css and "right:-6px" in css
    assert "justify-content:center" in css
    assert "stroke-width:2.6" in css
    assert "border:0" in css
    assert "width:min(94vw,1440px)" in css.replace(" ", "")
    assert "grid-template-columns:minmax(520px,1.15fr)minmax(420px,.85fr)" in css.replace(" ", "")
    assert "prompt-panel-body" in css and "max-height:min(34vh,320px)" in css.replace(" ", "")
    assert "prompt-edit-textarea" in css
    assert ".detail-side-actions" in css


def test_detail_modal_tag_unlink_and_add_controls_are_hover_and_touch_aware():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "detail-tag-chip" in detail
    assert "tag-unlink-button" in detail
    assert "add-tag-chip" in detail
    assert "tag-add-input" in detail
    assert "filteredTagSuggestions" in detail
    assert "api.updateItem(item.id" in detail
    assert "item.tags.filter" in detail
    assert ".detail-tag-chip .tag-unlink-button" in css
    assert ".detail-tag-chip:hover .tag-unlink-button" in css
    assert "@media(hover:none),(pointer:coarse)" in compact_css
    assert ".add-tag-chip" in css
    assert ".tag-add-popover" in css


def test_editor_supports_multilingual_prompts_collection_suggestions_and_image_requirements():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "clusters={clusters}" in app
    assert "tags={tags}" in app
    assert "clusters: ClusterRecord[]" in editor
    assert "tags: TagRecord[]" in editor
    assert "initialTraditionalPrompt" in editor
    assert "promptText(item, 'zh_hant') || promptText(item, 'original')" in editor
    assert "zhHantPrompt" in editor and "zhHansPrompt" in editor and "englishPrompt" in editor
    assert "language: 'en', text: englishPrompt.trim(), is_primary: true" in editor
    assert "language: 'zh_hant'" in editor
    assert "language: 'zh_hans'" in editor
    assert editor.index("t('englishPrompt')") < editor.index("t('traditionalChinesePrompt')") < editor.index("t('simplifiedChinesePrompt')")
    assert "model" in editor and "setModel" in editor
    assert "author" in editor and "setAuthor" in editor
    assert "sourceUrl" in editor and "setSourceUrl" in editor
    assert "notes" in editor and "setNotes" in editor
    assert "t('imageGeneratedFrom')" in editor
    assert "t('author')" in editor
    assert "t('sourceUrl')" in editor
    assert "t('notes')" in editor
    assert "collection-suggestions" in editor
    assert "filteredClusters" in editor
    assert "list=\"collection-suggestions\"" in editor
    assert "tag-suggestions" in editor
    assert "filteredTags" in editor
    assert "list=\"tag-suggestions\"" in editor
    assert "Original" not in detail
    assert "'original'" not in detail
    assert "t('resultImageRequired')" in editor and "required" in editor
    assert "t('referencePhotoOptional')" in editor and "optional" in i18n.lower()
    assert "resultFile" in editor and "referenceFile" in editor
    assert "hasExistingResultImage" in editor
    assert "image.role === 'result_image'" in editor
    assert "missingRequiredImage" in editor
    assert "createdNewItem" in editor
    assert "api.deleteItem(saved.id)" in editor
    assert "result_image" in types
    assert "reference_image" in types
    assert "role?: UploadImageRole" in types
    assert "fd.set('role', role)" in api_client


def test_frontend_prefers_result_image_for_card_and_detail_hero():
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    image_utils = (ROOT / "frontend" / "src" / "utils" / "images.ts").read_text()

    assert "selectPrimaryImage" in card
    assert "selectPrimaryImage" in detail
    assert "selectPrimaryImage" in explore
    assert "image?.role === 'result_image'" in image_utils
    assert "item.first_image?.thumb_path" not in card
    assert "const primaryImage = uniqueImages[0]" not in detail


def test_delete_action_archives_item_and_refreshes_visible_data():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()

    assert "deleteItem" in api_client
    assert "method: 'DELETE'" in api_client
    assert "onDeleted" in app
    assert "setItemsReloadKey(k => k + 1)" in app
    assert "t('deleteReference')" in editor
    assert "confirm(t('deleteReferenceConfirm'))" in editor
    assert "api.deleteItem(item.id)" in editor
    assert "danger" in editor
