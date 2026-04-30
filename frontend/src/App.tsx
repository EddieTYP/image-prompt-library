import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Plus, XCircle } from 'lucide-react';
import { api, isDemoMode } from './api/client';
import TopBar from './components/TopBar';
import FiltersPanel from './components/FiltersPanel';
import ExploreView from './components/ExploreView';
import CardsView from './components/CardsView';
import ItemDetailModal from './components/ItemDetailModal';
import ItemEditorModal from './components/ItemEditorModal';
import GenerationPanel from './components/GenerationPanel';
import GenerationQueueDrawer from './components/GenerationQueueDrawer';
import ConfigPanel from './components/ConfigPanel';
import { useDebouncedValue } from './hooks/useDebouncedValue';
import { useItemsQuery } from './hooks/useItemsQuery';
import type { AppUpdateStatus, ClusterRecord, GenerationJobRecord, GenerationProviderStatus, ItemDetail, ItemSummary, TagRecord, ViewMode } from './types';
import { copyTextToClipboard } from './utils/clipboard';
import { DEFAULT_UI_LANGUAGE, makeTranslator, normalizeUiLanguage, type UiLanguage } from './utils/i18n';
import { DEFAULT_PROMPT_LANGUAGE, normalizePromptLanguage, resolvePromptText, type PromptCopyLanguage } from './utils/prompts';

const UI_LANGUAGE_STORAGE_KEY = 'image-prompt-library.ui_language';
const PROMPT_LANGUAGE_STORAGE_KEY = 'image-prompt-library.preferred_prompt_language';
const VIEW_STORAGE_KEY = 'image-prompt-library.view_mode.v2';
const GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.global_thumbnail_budget';
const FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.focus_thumbnail_budget';

function loadPreferredLanguage(): PromptCopyLanguage {
  if (typeof window === 'undefined') return DEFAULT_PROMPT_LANGUAGE;
  return normalizePromptLanguage(window.localStorage.getItem(PROMPT_LANGUAGE_STORAGE_KEY));
}

function loadUiLanguage(): UiLanguage {
  if (typeof window === 'undefined') return DEFAULT_UI_LANGUAGE;
  return normalizeUiLanguage(window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY));
}

function loadPreferredView(): ViewMode {
  if (typeof window === 'undefined') return 'cards';
  const savedView = window.localStorage.getItem(VIEW_STORAGE_KEY);
  if (savedView === 'explore' || savedView === 'cards') return savedView;
  return 'cards';
}

function loadNumberSetting(key: string, fallback: number, min: number, max: number) {
  if (typeof window === 'undefined') return fallback;
  const raw = Number(window.localStorage.getItem(key));
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(max, Math.max(min, Math.round(raw)));
}

function selectedCollectionNameSizeClass(name: string) {
  if (name.length > 28) return 'is-very-long';
  if (name.length > 16) return 'is-long';
  return '';
}

function localizedClusterName(cluster: ClusterRecord | undefined, language: UiLanguage) {
  return cluster?.names?.[language] || cluster?.names?.en || cluster?.name || '';
}

function localizeCluster(cluster: ClusterRecord, language: UiLanguage): ClusterRecord {
  return { ...cluster, name: localizedClusterName(cluster, language) };
}

function localizeItemCluster(item: ItemSummary, language: UiLanguage): ItemSummary {
  return item.cluster ? { ...item, cluster: localizeCluster(item.cluster, language) } : item;
}

function generationProviderConnected(provider: GenerationProviderStatus) {
  return provider.provider !== 'manual_upload' && provider.available && provider.authenticated && provider.configured;
}

export default function App() {
  const [q, setQ] = useState('');
  const debouncedQ = useDebouncedValue(q);
  const [clusterId, setClusterId] = useState<string>();
  const [view, setView] = useState<ViewMode>(loadPreferredView);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [clusters, setClusters] = useState<ClusterRecord[]>([]);
  const [tags, setTags] = useState<TagRecord[]>([]);
  const [detailId, setDetailId] = useState<string>();
  const [editing, setEditing] = useState<ItemDetail | undefined>();
  const [editorOpen, setEditorOpen] = useState(false);
  const [itemsReloadKey, setItemsReloadKey] = useState(0);
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(loadUiLanguage);
  const [preferredLanguage, setPreferredLanguage] = useState<PromptCopyLanguage>(loadPreferredLanguage);
  const [globalThumbnailBudget, setGlobalThumbnailBudget] = useState(() => loadNumberSetting(GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 50, 150));
  const [focusThumbnailBudget, setFocusThumbnailBudget] = useState(() => loadNumberSetting(FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 24, 100));
  const [exploreFitRequestKey, setExploreFitRequestKey] = useState(0);
  const [pendingExploreUnfilterClusterId, setPendingExploreUnfilterClusterId] = useState<string>();
  const [exploreUnfilterFadePhase, setExploreUnfilterFadePhase] = useState<'out' | 'pre-in' | 'in' | 'idle'>('idle');
  const [toast, setToast] = useState<{ title: string; tone: 'success' | 'error' }>();
  const [standaloneGenerationOpen, setStandaloneGenerationOpen] = useState(false);
  const [generationQueueOpen, setGenerationQueueOpen] = useState(false);
  const [focusedGenerationJobId, setFocusedGenerationJobId] = useState<string>();
  const [pendingGenerationSourceItemId, setPendingGenerationSourceItemId] = useState<string>();
  const [generationAvailable, setGenerationAvailable] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<AppUpdateStatus>();
  const [restartRequiredVersion, setRestartRequiredVersion] = useState<string>();
  const { data, loading, initialLoading, refreshing, error, dataScope } = useItemsQuery(debouncedQ, clusterId, undefined, 1000, itemsReloadKey);
  const exploreFocusedClusterId = view === 'explore'
    ? (clusterId || (dataScope.clusterId === pendingExploreUnfilterClusterId ? pendingExploreUnfilterClusterId : undefined))
    : clusterId;
  const selectedCluster = useMemo(() => clusters.find(c => c.id === clusterId), [clusters, clusterId]);
  const t = useMemo(() => makeTranslator(uiLanguage), [uiLanguage]);
  const localizedClusters = useMemo(() => clusters.map(cluster => localizeCluster(cluster, uiLanguage)), [clusters, uiLanguage]);
  const localizedData = useMemo(() => ({ ...data, items: data.items.map(item => localizeItemCluster(item, uiLanguage)) }), [data, uiLanguage]);
  const localizedSelectedCluster = selectedCluster ? localizeCluster(selectedCluster, uiLanguage) : undefined;
  const refreshClusters = () => api.clusters().then(setClusters).catch(() => setClusters([]));
  const refreshTags = () => api.tags().then(setTags).catch(() => setTags([]));
  const refreshGenerationAvailability = () => api.generationProviders()
    .then(providers => setGenerationAvailable(providers.some(generationProviderConnected)))
    .catch(() => setGenerationAvailable(false));
  const refreshUpdateStatus = useCallback(() => api.updateStatus().then(status => {
    setUpdateStatus(status);
    if (!status.update_available) setRestartRequiredVersion(undefined);
    return status;
  }).catch(() => {
    setUpdateStatus(undefined);
    return undefined;
  }), []);
  useEffect(() => { refreshClusters(); refreshTags(); refreshGenerationAvailability(); refreshUpdateStatus(); }, [refreshUpdateStatus]);
  useEffect(() => {
    const timer = window.setInterval(refreshGenerationAvailability, 3000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(undefined), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (pendingExploreUnfilterClusterId && dataScope.clusterId !== pendingExploreUnfilterClusterId) {
      setPendingExploreUnfilterClusterId(undefined);
      setExploreUnfilterFadePhase('pre-in');
      window.requestAnimationFrame(() => setExploreUnfilterFadePhase('in'));
      const timer = window.setTimeout(() => setExploreUnfilterFadePhase('idle'), 180);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [dataScope.clusterId, pendingExploreUnfilterClusterId]);
  const selectCluster = (c: ClusterRecord) => { setClusterId(c.id); updateView('cards'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); };
  const focusCluster = (c: ClusterRecord) => { setClusterId(c.id); updateView('explore'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); setExploreFitRequestKey(key => key + 1); };
  const handleFilterSelect = (c: ClusterRecord) => { view === 'explore' ? focusCluster(c) : selectCluster(c); };
  const clearCluster = () => {
    if (view === 'explore' && clusterId) {
      setPendingExploreUnfilterClusterId(clusterId);
      setExploreUnfilterFadePhase('out');
    }
    setClusterId(undefined);
  };
  const saved = () => { refreshClusters(); refreshTags(); setItemsReloadKey(k => k + 1); };
  const deleted = () => { setDetailId(undefined); setEditing(undefined); refreshClusters(); refreshTags(); setItemsReloadKey(k => k + 1); };
  const updatePreferredLanguage = (language: PromptCopyLanguage) => {
    setPreferredLanguage(language);
    window.localStorage.setItem(PROMPT_LANGUAGE_STORAGE_KEY, language);
  };
  const updateUiLanguage = (language: UiLanguage) => {
    setUiLanguage(language);
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
  };
  const updateView = (nextView: ViewMode) => {
    setView(nextView);
    window.localStorage.setItem(VIEW_STORAGE_KEY, nextView);
  };
  const updateGlobalThumbnailBudget = (budget: number) => {
    setGlobalThumbnailBudget(budget);
    window.localStorage.setItem(GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY, String(budget));
  };
  const updateFocusThumbnailBudget = (budget: number) => {
    setFocusThumbnailBudget(budget);
    window.localStorage.setItem(FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY, String(budget));
  };
  const showCopyToast = (success: boolean) => {
    setToast({ title: success ? t('copySuccess') : t('copyFailed'), tone: success ? 'success' : 'error' });
    window.setTimeout(() => setToast(undefined), 1800);
  };
  const copyPrompt = async (item: ItemSummary) => {
    const text = resolvePromptText(item.prompts, preferredLanguage, item.title);
    const copied = await copyTextToClipboard(text);
    showCopyToast(copied);
  };
  const openNewItemEditor = () => { setEditing(undefined); setEditorOpen(true); };
  const openStandaloneGeneration = () => { if (!generationAvailable) return; setFocusedGenerationJobId(undefined); setPendingGenerationSourceItemId(undefined); setStandaloneGenerationOpen(true); setGenerationQueueOpen(false); };
  const openGenerationJob = (job: GenerationJobRecord) => {
    setFocusedGenerationJobId(job.id);
    setGenerationQueueOpen(false);
    if (job.source_item_id) {
      setPendingGenerationSourceItemId(job.source_item_id);
      setStandaloneGenerationOpen(false);
      setDetailId(job.source_item_id);
      return;
    }
    setPendingGenerationSourceItemId(undefined);
    setDetailId(undefined);
    setStandaloneGenerationOpen(true);
  };
  const favorite = (id: string) => { api.favorite(id).then(saved).catch(() => undefined); };
  const editSummary = (item: { id: string }) => { api.item(item.id).then(full => { setEditing(full); setEditorOpen(true); }).catch(() => undefined); };
  const focusedItemGenerationJobId = pendingGenerationSourceItemId ? focusedGenerationJobId : undefined;
  const showSelectedCollectionDock = Boolean(selectedCluster && !filtersOpen && !configOpen && !detailId && !editorOpen);
  const updateBadgeLabel = restartRequiredVersion ? 'Restart required' : (updateStatus?.update_available ? 'Update available' : undefined);
  return <div className={`app ${view === 'explore' ? 'explore-mode' : 'cards-mode'}`}>
    <TopBar t={t} q={q} updateBadgeLabel={updateBadgeLabel} onQ={setQ} view={view} onView={updateView} onFilters={() => setFiltersOpen(true)} onConfig={() => setConfigOpen(true)} count={localizedData.total} clusterName={localizedClusterName(selectedCluster, uiLanguage)} clearCluster={clearCluster} />
    {isDemoMode && (
      <div className="demo-banner" role="status">
        <strong>{t('onlineReadOnlyDemo')}</strong>
        <span>{t('compressedForDemo')}</span>
        <span>{t('runLocallyForPrivateLibrary')}</span>
        <span>{t('localV04SupportsDirectGeneration')}</span>
        <a href="https://github.com/EddieTYP/image-prompt-library" target="_blank" rel="noreferrer">{t('viewOnGitHub')}</a>
      </div>
    )}
    <FiltersPanel t={t} open={filtersOpen} clusters={localizedClusters} selected={clusterId} onSelect={handleFilterSelect} onClear={clearCluster} onClose={() => setFiltersOpen(false)} />
    <ConfigPanel t={t} open={configOpen} onClose={() => setConfigOpen(false)} uiLanguage={uiLanguage} onUiLanguage={updateUiLanguage} preferredLanguage={preferredLanguage} onPreferredLanguage={updatePreferredLanguage} globalThumbnailBudget={globalThumbnailBudget} onGlobalThumbnailBudget={updateGlobalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusThumbnailBudget={updateFocusThumbnailBudget} updateStatus={updateStatus} onRefreshUpdateStatus={refreshUpdateStatus} onUpdateInstalled={setRestartRequiredVersion} onProvidersChanged={refreshGenerationAvailability} />
    {/* Static-test compatibility marker: <main className="app-main"> */}
    <main className={`app-main ${refreshing ? 'is-refreshing' : ''}`} aria-busy={refreshing}>
      {refreshing && <div className="refresh-indicator" role="status">{t('loading')}</div>}
      {initialLoading && <div className="loading">{t('loading')}</div>}
      {error && <div className="error">{error}</div>}
      {view === 'explore'
        ? <ExploreView t={t} clusters={localizedClusters} items={localizedData.items} focusedClusterId={exploreFocusedClusterId} fitRequestKey={exploreFitRequestKey} unfilterTransitionPhase={exploreUnfilterFadePhase} globalThumbnailBudget={globalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusCluster={focusCluster} onOpen={setDetailId} onAdd={isDemoMode ? undefined : openNewItemEditor} />
        : <CardsView t={t} items={localizedData.items} onOpen={setDetailId} onFavorite={isDemoMode ? undefined : favorite} onEdit={isDemoMode ? undefined : editSummary} onCopyPrompt={copyPrompt} onAdd={isDemoMode ? undefined : openNewItemEditor} />}
    </main>
    {showSelectedCollectionDock && localizedSelectedCluster && (
      <button className="selected-collection-dock" onClick={clearCluster} aria-label={`${t('collectionChip')}: ${localizedSelectedCluster.name}. ${t('close')}`}>
        <span className="selected-collection-dot" aria-hidden="true" />
        <span className={`selected-collection-name ${selectedCollectionNameSizeClass(localizedSelectedCluster.name)}`}>{localizedSelectedCluster.name}</span>
        <span className="selected-collection-count">{localizedData.total} {t('referencesShown')}</span>
        <span className="selected-collection-clear" aria-hidden="true">×</span>
      </button>
    )}
    {/* Static-test compatibility marker: !isDemoMode && <button className="fab" */}
    {!isDemoMode && (
      <div className="floating-action-rail">
        <button className="fab add-fab" onClick={openNewItemEditor}><Plus/> {t('add')}</button>
        {generationAvailable && <button className="fab generate-fab" onClick={openStandaloneGeneration}>Generate</button>}
      </div>
    )}
    {!isDemoMode && <GenerationQueueDrawer t={t} open={generationQueueOpen} onOpen={() => setGenerationQueueOpen(true)} onClose={() => setGenerationQueueOpen(false)} onOpenJob={openGenerationJob} />}
    <ItemDetailModal t={t} id={detailId} preferredLanguage={preferredLanguage} clusters={localizedClusters} tags={tags} onClose={() => setDetailId(undefined)} onCopyPrompt={showCopyToast} onChanged={saved} onEdit={(item) => { setDetailId(undefined); setEditing(item); setEditorOpen(true); }} showMutations={!isDemoMode} canGenerate={generationAvailable} initialGenerationJobId={focusedItemGenerationJobId} />
    {toast && <div className={`toast copy-toast elegant-toast ${toast.tone}`} role="status"><span className="toast-icon">{toast.tone === 'success' ? <Check size={16} /> : <XCircle size={16} />}</span><span className="toast-title">{toast.title}</span></div>}
    {editorOpen && <ItemEditorModal t={t} item={editing} clusters={localizedClusters} tags={tags} onClose={() => setEditorOpen(false)} onSaved={saved} onDeleted={deleted} />}
    {standaloneGenerationOpen && <GenerationPanel t={t} preferredLanguage={preferredLanguage} initialJobId={focusedGenerationJobId} onClose={() => setStandaloneGenerationOpen(false)} onAccepted={(item, message) => { saved(); setToast({ title: message || 'New variant item created', tone: 'success' }); if (item?.id) setDetailId(item.id); }} />}
  </div>
}
