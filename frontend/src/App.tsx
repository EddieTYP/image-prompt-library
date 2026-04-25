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
import type { ClusterRecord, ItemDetail, ItemSummary, ViewMode } from './types';
import { copyTextToClipboard } from './utils/clipboard';
import { DEFAULT_PROMPT_LANGUAGE, normalizePromptLanguage, resolvePromptText, type PromptLanguage } from './utils/prompts';

const PROMPT_LANGUAGE_STORAGE_KEY = 'image-prompt-library.preferred_prompt_language';
const GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.global_thumbnail_budget';
const FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.focus_thumbnail_budget';

function loadPreferredLanguage(): PromptLanguage {
  if (typeof window === 'undefined') return DEFAULT_PROMPT_LANGUAGE;
  return normalizePromptLanguage(window.localStorage.getItem(PROMPT_LANGUAGE_STORAGE_KEY));
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
  const [detailId, setDetailId] = useState<string>();
  const [editing, setEditing] = useState<ItemDetail | undefined>();
  const [editorOpen, setEditorOpen] = useState(false);
  const [itemsReloadKey, setItemsReloadKey] = useState(0);
  const [preferredLanguage, setPreferredLanguage] = useState<PromptLanguage>(loadPreferredLanguage);
  const [globalThumbnailBudget, setGlobalThumbnailBudget] = useState(() => loadNumberSetting(GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 50, 150));
  const [focusThumbnailBudget, setFocusThumbnailBudget] = useState(() => loadNumberSetting(FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 24, 100));
  const [toast, setToast] = useState<{ title: string; tone: 'success' | 'error' }>();
  const { data, loading, error } = useItemsQuery(debouncedQ, clusterId, undefined, 1000, itemsReloadKey);
  const selectedCluster = useMemo(() => clusters.find(c => c.id === clusterId), [clusters, clusterId]);
  const refreshClusters = () => api.clusters().then(setClusters).catch(() => setClusters([]));
  useEffect(() => { refreshClusters(); }, []);
  const selectCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('cards'); setFiltersOpen(false); };
  const focusCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('explore'); setFiltersOpen(false); };
  const handleFilterSelect = (c: ClusterRecord) => { view === 'explore' ? focusCluster(c) : selectCluster(c); };
  const openClusterAsCards = (c: ClusterRecord) => { setClusterId(c.id); setView('cards'); setFiltersOpen(false); };
  const clearCluster = () => setClusterId(undefined);
  const saved = () => { refreshClusters(); setItemsReloadKey(k => k + 1); };
  const updatePreferredLanguage = (language: PromptLanguage) => {
    setPreferredLanguage(language);
    window.localStorage.setItem(PROMPT_LANGUAGE_STORAGE_KEY, language);
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
    setToast({ title: success ? 'Prompt copied' : 'Copy failed', tone: success ? 'success' : 'error' });
    window.setTimeout(() => setToast(undefined), 1800);
  };
  const copyPrompt = async (item: ItemSummary) => {
    const text = resolvePromptText(item.prompts, preferredLanguage, item.title);
    const copied = await copyTextToClipboard(text);
    showCopyToast(copied);
  };
  const favorite = (id: string) => { api.favorite(id).then(saved).catch(() => undefined); };
  const editSummary = (item: { id: string }) => { api.item(item.id).then(full => { setEditing(full); setEditorOpen(true); }).catch(() => undefined); };
  return <div className="app">
    <TopBar q={q} onQ={setQ} view={view} onView={setView} onFilters={() => setFiltersOpen(true)} onConfig={() => setConfigOpen(true)} count={data.total} clusterName={selectedCluster?.name} clearCluster={clearCluster} />
    <FiltersPanel open={filtersOpen} clusters={clusters} selected={clusterId} onSelect={handleFilterSelect} onClear={clearCluster} onClose={() => setFiltersOpen(false)} />
    <ConfigPanel open={configOpen} onClose={() => setConfigOpen(false)} preferredLanguage={preferredLanguage} onPreferredLanguage={updatePreferredLanguage} globalThumbnailBudget={globalThumbnailBudget} onGlobalThumbnailBudget={updateGlobalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusThumbnailBudget={updateFocusThumbnailBudget} />
    <main>
      {loading && <div className="loading">Loading…</div>}
      {error && <div className="error">{error}</div>}
      {view === 'explore'
        ? <ExploreView clusters={clusters} items={data.items} focusedClusterId={clusterId} globalThumbnailBudget={globalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusCluster={focusCluster} onOpenClusterCards={openClusterAsCards} onOpen={setDetailId} />
        : <CardsView items={data.items} onOpen={setDetailId} onFavorite={favorite} onEdit={editSummary} onCopyPrompt={copyPrompt} />}
    </main>
    <button className="fab" onClick={() => { setEditing(undefined); setEditorOpen(true); }}><Plus/> Add</button>
    <ItemDetailModal id={detailId} preferredLanguage={preferredLanguage} onClose={() => setDetailId(undefined)} onCopyPrompt={showCopyToast} onEdit={(item) => { setDetailId(undefined); setEditing(item); setEditorOpen(true); }} />
    {toast && <div className={`toast copy-toast elegant-toast ${toast.tone}`} role="status"><span className="toast-icon">{toast.tone === 'success' ? <Check size={16} /> : <XCircle size={16} />}</span><span className="toast-title">{toast.title}</span></div>}
    {editorOpen && <ItemEditorModal item={editing} onClose={() => setEditorOpen(false)} onSaved={saved} />}
  </div>
}
