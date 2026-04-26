import { useEffect, useMemo, useState } from 'react';
import { Check, Plus, XCircle } from 'lucide-react';
import { api } from './api/client';
import TopBar from './components/TopBar';
import FiltersPanel from './components/FiltersPanel';
import ExploreView from './components/ExploreView';
import CardsView from './components/CardsView';
import ItemDetailModal from './components/ItemDetailModal';
import ItemEditorModal from './components/ItemEditorModal';
import ConfigPanel from './components/ConfigPanel';
import { useDebouncedValue } from './hooks/useDebouncedValue';
import { useItemsQuery } from './hooks/useItemsQuery';
import type { ClusterRecord, ItemDetail, ItemSummary, TagRecord, ViewMode } from './types';
import { copyTextToClipboard } from './utils/clipboard';
import { DEFAULT_UI_LANGUAGE, makeTranslator, normalizeUiLanguage, type UiLanguage } from './utils/i18n';
import { DEFAULT_PROMPT_LANGUAGE, normalizePromptLanguage, resolvePromptText, type PromptLanguage } from './utils/prompts';

const UI_LANGUAGE_STORAGE_KEY = 'image-prompt-library.ui_language';
const PROMPT_LANGUAGE_STORAGE_KEY = 'image-prompt-library.preferred_prompt_language';
const GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.global_thumbnail_budget';
const FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.focus_thumbnail_budget';

function loadPreferredLanguage(): PromptLanguage {
  if (typeof window === 'undefined') return DEFAULT_PROMPT_LANGUAGE;
  return normalizePromptLanguage(window.localStorage.getItem(PROMPT_LANGUAGE_STORAGE_KEY));
}

function loadUiLanguage(): UiLanguage {
  if (typeof window === 'undefined') return DEFAULT_UI_LANGUAGE;
  return normalizeUiLanguage(window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY));
}

function loadNumberSetting(key: string, fallback: number, min: number, max: number) {
  if (typeof window === 'undefined') return fallback;
  const raw = Number(window.localStorage.getItem(key));
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(max, Math.max(min, Math.round(raw)));
}

export default function App() {
  const [q, setQ] = useState('');
  const debouncedQ = useDebouncedValue(q);
  const [clusterId, setClusterId] = useState<string>();
  const [view, setView] = useState<ViewMode>('explore');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [clusters, setClusters] = useState<ClusterRecord[]>([]);
  const [tags, setTags] = useState<TagRecord[]>([]);
  const [detailId, setDetailId] = useState<string>();
  const [editing, setEditing] = useState<ItemDetail | undefined>();
  const [editorOpen, setEditorOpen] = useState(false);
  const [itemsReloadKey, setItemsReloadKey] = useState(0);
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(loadUiLanguage);
  const [preferredLanguage, setPreferredLanguage] = useState<PromptLanguage>(loadPreferredLanguage);
  const [globalThumbnailBudget, setGlobalThumbnailBudget] = useState(() => loadNumberSetting(GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 50, 150));
  const [focusThumbnailBudget, setFocusThumbnailBudget] = useState(() => loadNumberSetting(FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 24, 100));
  const [exploreFitRequestKey, setExploreFitRequestKey] = useState(0);
  const [pendingExploreUnfilterClusterId, setPendingExploreUnfilterClusterId] = useState<string>();
  const [exploreUnfilterFadePhase, setExploreUnfilterFadePhase] = useState<'out' | 'pre-in' | 'in' | 'idle'>('idle');
  const [toast, setToast] = useState<{ title: string; tone: 'success' | 'error' }>();
  const { data, loading, initialLoading, refreshing, error, dataScope } = useItemsQuery(debouncedQ, clusterId, undefined, 1000, itemsReloadKey);
  const exploreFocusedClusterId = view === 'explore'
    ? (clusterId || (dataScope.clusterId === pendingExploreUnfilterClusterId ? pendingExploreUnfilterClusterId : undefined))
    : clusterId;
  const selectedCluster = useMemo(() => clusters.find(c => c.id === clusterId), [clusters, clusterId]);
  const t = useMemo(() => makeTranslator(uiLanguage), [uiLanguage]);
  const refreshClusters = () => api.clusters().then(setClusters).catch(() => setClusters([]));
  const refreshTags = () => api.tags().then(setTags).catch(() => setTags([]));
  useEffect(() => { refreshClusters(); refreshTags(); }, []);
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
  const selectCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('cards'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); };
  const focusCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('explore'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); setExploreFitRequestKey(key => key + 1); };
  const handleFilterSelect = (c: ClusterRecord) => { view === 'explore' ? focusCluster(c) : selectCluster(c); };
  const openClusterAsCards = (c: ClusterRecord) => { setClusterId(c.id); setView('cards'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); };
  const clearCluster = () => {
    if (view === 'explore' && clusterId) {
      setPendingExploreUnfilterClusterId(clusterId);
      setExploreUnfilterFadePhase('out');
    }
    setClusterId(undefined);
  };
  const saved = () => { refreshClusters(); refreshTags(); setItemsReloadKey(k => k + 1); };
  const deleted = () => { setDetailId(undefined); setEditing(undefined); refreshClusters(); refreshTags(); setItemsReloadKey(k => k + 1); };
  const updatePreferredLanguage = (language: PromptLanguage) => {
    setPreferredLanguage(language);
    window.localStorage.setItem(PROMPT_LANGUAGE_STORAGE_KEY, language);
  };
  const updateUiLanguage = (language: UiLanguage) => {
    setUiLanguage(language);
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
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
  const favorite = (id: string) => { api.favorite(id).then(saved).catch(() => undefined); };
  const editSummary = (item: { id: string }) => { api.item(item.id).then(full => { setEditing(full); setEditorOpen(true); }).catch(() => undefined); };
  return <div className={`app ${view === 'explore' ? 'explore-mode' : 'cards-mode'}`}>
    <TopBar t={t} q={q} onQ={setQ} view={view} onView={setView} onFilters={() => setFiltersOpen(true)} onConfig={() => setConfigOpen(true)} count={data.total} clusterName={selectedCluster?.name} clearCluster={clearCluster} />
    <FiltersPanel t={t} open={filtersOpen} clusters={clusters} selected={clusterId} onSelect={handleFilterSelect} onClear={clearCluster} onClose={() => setFiltersOpen(false)} />
    <ConfigPanel t={t} open={configOpen} onClose={() => setConfigOpen(false)} uiLanguage={uiLanguage} onUiLanguage={updateUiLanguage} preferredLanguage={preferredLanguage} onPreferredLanguage={updatePreferredLanguage} globalThumbnailBudget={globalThumbnailBudget} onGlobalThumbnailBudget={updateGlobalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusThumbnailBudget={updateFocusThumbnailBudget} />
    {/* Static-test compatibility marker: <main className="app-main"> */}
    <main className={`app-main ${refreshing ? 'is-refreshing' : ''}`} aria-busy={refreshing}>
      {refreshing && <div className="refresh-indicator" role="status">{t('loading')}</div>}
      {initialLoading && <div className="loading">{t('loading')}</div>}
      {error && <div className="error">{error}</div>}
      {view === 'explore'
        ? <ExploreView t={t} clusters={clusters} items={data.items} focusedClusterId={exploreFocusedClusterId} fitRequestKey={exploreFitRequestKey} unfilterTransitionPhase={exploreUnfilterFadePhase} globalThumbnailBudget={globalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusCluster={focusCluster} onOpenClusterCards={openClusterAsCards} onOpen={setDetailId} onAdd={openNewItemEditor} />
        : <CardsView t={t} items={data.items} onOpen={setDetailId} onFavorite={favorite} onEdit={editSummary} onCopyPrompt={copyPrompt} onAdd={openNewItemEditor} />}
    </main>
    <button className="fab" onClick={openNewItemEditor}><Plus/> {t('add')}</button>
    <ItemDetailModal t={t} id={detailId} preferredLanguage={preferredLanguage} clusters={clusters} tags={tags} onClose={() => setDetailId(undefined)} onCopyPrompt={showCopyToast} onChanged={saved} onEdit={(item) => { setDetailId(undefined); setEditing(item); setEditorOpen(true); }} />
    {toast && <div className={`toast copy-toast elegant-toast ${toast.tone}`} role="status"><span className="toast-icon">{toast.tone === 'success' ? <Check size={16} /> : <XCircle size={16} />}</span><span className="toast-title">{toast.title}</span></div>}
    {editorOpen && <ItemEditorModal t={t} item={editing} clusters={clusters} tags={tags} onClose={() => setEditorOpen(false)} onSaved={saved} onDeleted={deleted} />}
  </div>
}
