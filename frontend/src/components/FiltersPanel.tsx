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
  const total = clusters.reduce((sum, cluster) => sum + cluster.count, 0);

  return (
    <aside className={`drawer filter-drawer ${open ? 'open' : ''}`} aria-label="Filters">
      <div className="drawer-head filter-drawer-head">
        <div>
          <p className="drawer-eyebrow"><SlidersHorizontal size={15} /> Filters</p>
          <h2>Templates</h2>
        </div>
        <button onClick={onClose} aria-label="Close filters"><X /></button>
      </div>

      <div className="filter-search" aria-hidden="true">
        <Search size={17} />
        <span>Search templates by collection</span>
      </div>

      <p className="muted filter-help">Use clusters as quick filter chips, similar to VistaCreate template filters.</p>

      <div className="filter-pill-grid" aria-label="Template collections">
        <button className={!selected ? 'selected' : ''} onClick={onClear}>
          <span>All references</span>
          <b>{total}</b>
        </button>
        {clusters.map(cluster => (
          <button key={cluster.id} className={selected === cluster.id ? 'selected' : ''} onClick={() => onSelect(cluster)}>
            <span>{cluster.name}</span>
            <b>{cluster.count}</b>
          </button>
        ))}
      </div>
    </aside>
  );
}
