import { useMemo, useState } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import type { ClusterRecord } from '../types';
import type { Translator } from '../utils/i18n';

export default function FiltersPanel({
  open,
  t,
  clusters,
  selected,
  onSelect,
  onClear,
  onClose,
}: {
  open: boolean;
  t: Translator;
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
    <aside className={`drawer filter-drawer ${open ? 'open' : ''}`} aria-label={t('filters')}>
      <div className="drawer-head filter-drawer-head">
        <div>
          <p className="drawer-eyebrow"><SlidersHorizontal size={15} /> {t('filters')}</p>
          <h2>{t('collections')}</h2>
        </div>
        <button className="panel-close" onClick={onClose} aria-label={t('closeFilters')}><X size={18} /></button>
      </div>

      <label className="filter-search">
        <Search size={17} />
        <input
          value={collectionQuery}
          onChange={event => setCollectionQuery(event.currentTarget.value)}
          placeholder={t('searchCollections')}
          aria-label={t('searchCollections')}
        />
      </label>

      <div className="filter-pill-grid" aria-label={t('collectionFilters')}>
        <button className={!selected ? 'selected' : ''} onClick={onClear}>
          <span>{t('allReferences')}</span>
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
        <div className="filter-empty">{t('noCollectionsFound')}</div>
      )}
    </aside>
  );
}
