import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
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
import type { ClusterRecord, ItemDetail, ViewMode } from './types';

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
  const { data, loading, error } = useItemsQuery(debouncedQ, clusterId, undefined, 300, itemsReloadKey);
  const selectedCluster = useMemo(() => clusters.find(c => c.id === clusterId), [clusters, clusterId]);
  const refreshClusters = () => api.clusters().then(setClusters).catch(() => setClusters([]));
  useEffect(() => { refreshClusters(); }, []);
  const selectCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('cards'); setFiltersOpen(false); };
  const focusCluster = (c: ClusterRecord) => { setClusterId(c.id); setView('explore'); setFiltersOpen(false); };
  const clearCluster = () => setClusterId(undefined);
  const saved = () => { refreshClusters(); setItemsReloadKey(k => k + 1); };
  const favorite = (id: string) => { api.favorite(id).then(saved).catch(() => undefined); };
  const editSummary = (item: { id: string }) => { api.item(item.id).then(full => { setEditing(full); setEditorOpen(true); }).catch(() => undefined); };
  return <div className="app">
    <TopBar q={q} onQ={setQ} view={view} onView={setView} onFilters={() => setFiltersOpen(true)} onConfig={() => setConfigOpen(true)} count={data.total} clusterName={selectedCluster?.name} clearCluster={clearCluster} />
    <FiltersPanel open={filtersOpen} clusters={clusters} selected={clusterId} onSelect={selectCluster} onClose={() => setFiltersOpen(false)} />
    <ConfigPanel open={configOpen} onClose={() => setConfigOpen(false)} />
    <main>
      {loading && <div className="loading">Loading…</div>}
      {error && <div className="error">{error}</div>}
      {view === 'explore'
        ? <ExploreView clusters={clusters} items={data.items} focusedClusterId={clusterId} onFocusCluster={focusCluster} onOpen={setDetailId} />
        : <CardsView items={data.items} onOpen={setDetailId} onFavorite={favorite} onEdit={editSummary} />}
    </main>
    <button className="fab" onClick={() => { setEditing(undefined); setEditorOpen(true); }}><Plus/> Add</button>
    <ItemDetailModal id={detailId} onClose={() => setDetailId(undefined)} onEdit={(item) => { setDetailId(undefined); setEditing(item); setEditorOpen(true); }} />
    {editorOpen && <ItemEditorModal item={editing} onClose={() => setEditorOpen(false)} onSaved={saved} />}
  </div>
}
