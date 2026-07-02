import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
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
  const drawerRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const total = clusters.reduce((sum, cluster) => sum + cluster.count, 0);
  const normalizedQuery = collectionQuery.trim().toLowerCase();
  const filteredClusters = useMemo(
    () => normalizedQuery
      ? clusters.filter(cluster => cluster.name.toLowerCase().includes(normalizedQuery))
      : clusters,
    [clusters, normalizedQuery],
  );

  useEffect(() => {
    if (!open) return;
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement && !drawerRef.current?.contains(activeElement)) {
      openerRef.current = activeElement;
    }

    const focusTarget = searchInputRef.current || closeButtonRef.current;
    window.setTimeout(() => {
      focusTarget?.focus({ preventScroll: true });
    }, 0);
  }, [open]);

  const closePanel = () => {
    onClose();
    window.setTimeout(() => openerRef.current?.focus({ preventScroll: true }), 0);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closePanel();
    }
  };

  return (
    <aside
      ref={drawerRef}
      className={`drawer filter-drawer ${open ? 'open' : ''}`}
      aria-label={t('filters')}
      aria-hidden={!open}
      inert={!open}
      onKeyDown={handleKeyDown}
    >
      <div className="drawer-head filter-drawer-head">
        <div>
          <p className="drawer-eyebrow"><SlidersHorizontal size={15} /> {t('filters')}</p>
          <h2>{t('collections')}</h2>
        </div>
        <button
          ref={closeButtonRef}
          className="panel-close"
          onClick={closePanel}
          aria-label={t('closeFilters')}
          tabIndex={open ? 0 : -1}
        >
          <X size={20} strokeWidth={2.25} />
        </button>
      </div>

      <label className="filter-search">
        <Search size={17} />
        <input
          ref={searchInputRef}
          value={collectionQuery}
          onChange={event => setCollectionQuery(event.currentTarget.value)}
          placeholder={t('searchCollections')}
          aria-label={t('searchCollections')}
          tabIndex={open ? 0 : -1}
        />
      </label>

      <div className="filter-pill-grid" aria-label={t('collectionFilters')}>
        <button
          className={!selected ? 'selected' : ''}
          onClick={onClear}
          tabIndex={open ? 0 : -1}
        >
          <span>{t('allReferences')}</span>
          <b>{total}</b>
        </button>
        {filteredClusters.map(cluster => (
          <button
            key={cluster.id}
            className={selected === cluster.id ? 'selected' : ''}
            onClick={() => onSelect(cluster)}
            tabIndex={open ? 0 : -1}
          >
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
