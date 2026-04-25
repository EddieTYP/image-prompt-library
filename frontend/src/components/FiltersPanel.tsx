import { useMemo, useState } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import type { ClusterRecord } from '../types';

export default function FiltersPanel({
  open,
  clusters,
  selected,
  onSelect,
  onClear,
  onClose,
}: {
  open: boolean;
  clusters: ClusterRecord[];
  selected?: string;
  onSelect: (c: ClusterRecord) => void;
  onClear: () => void;
  onClose: () => void;
}) {
  const [collectionQuery, setCollectionQuery] = useState('');
  const total = clusters.reduce((sum, cluster) => sum + cluster.count, 0);
  const normalizedQuery = collectionQuery.trim().toLowerCase();
  const filteredClusters = useMemo(
    () => normalizedQuery
      ? clusters.filter(cluster => cluster.name.toLowerCase().includes(normalizedQuery))
      : clusters,
    [clusters, normalizedQuery],
  );

  return (
    <aside className={`drawer filter-drawer ${open ? 'open' : ''}`} aria-label="Filters">
      <div className="drawer-head filter-drawer-head">
        <div>
          <p className="drawer-eyebrow"><SlidersHorizontal size={15} /> Filters</p>
          <h2>Collections</h2>
        </div>
        <button className="panel-close" onClick={onClose} aria-label="Close filters"><X size={18} /></button>
      </div>

      <label className="filter-search">
        <Search size={17} />
        <input
          value={collectionQuery}
          onChange={event => setCollectionQuery(event.currentTarget.value)}
          placeholder="Search collections"
          aria-label="Search collections"
        />
      </label>

      <div className="filter-pill-grid" aria-label="Collection filters">
        <button className={!selected ? 'selected' : ''} onClick={onClear}>
          <span>All references</span>
          <b>{total}</b>
        </button>
        {filteredClusters.map(cluster => (
          <button key={cluster.id} className={selected === cluster.id ? 'selected' : ''} onClick={() => onSelect(cluster)}>
            <span>{cluster.name}</span>
            <b>{cluster.count}</b>
          </button>
        ))}
      </div>
      {filteredClusters.length === 0 && (
        <div className="filter-empty">No collections found</div>
      )}
    </aside>
  );
}
