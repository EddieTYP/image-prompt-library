import { Filter, Search, Settings } from 'lucide-react';
import headerLogo from '../assets/header-logo.png';
import type { ItemSortMode, ViewMode } from '../types';
import type { Translator } from '../utils/i18n';
import ViewToggle from './ViewToggle';

interface Props {
  q: string;
  t: Translator;
  searchQuery?: string;
  sort: ItemSortMode;
  sortLabel?: string;
  queryFilterChips: string[];
  updateBadgeLabel?: string;
  onQ: (v: string) => void;
  onSort: (sort: ItemSortMode) => void;
  onClearSort?: () => void;
  view: ViewMode;
  onView: (v: ViewMode) => void;
  onFilters: () => void;
  onConfig: () => void;
  count: number;
  clusterName?: string;
  clearCluster: () => void;
}

export default function TopBar({
  q,
  t,
  searchQuery,
  sort,
  sortLabel,
  queryFilterChips,
  updateBadgeLabel,
  onQ,
  onSort,
  onClearSort,
  view,
  onView,
  onFilters,
  onConfig,
  count,
  clusterName,
  clearCluster,
}: Props) {
  const hasActiveFilter = Boolean(clusterName);
  return (
    <header className="chrome">
      <nav className="nav-row" aria-label={t('primaryNavigation')}>
        <button className={`vista-button filter-button${hasActiveFilter ? ' active' : ''}`} onClick={onFilters}>
          <Filter size={18} />
          <span className="filter-label">{t('filters')}</span>
        </button>

        <label className="search toolbar-search" aria-label={t('searchAria')}>
          <Search size={20} />
          <input
            value={q}
            onChange={e => onQ(e.target.value)}
            placeholder={t('searchPlaceholder')}
            autoFocus
          />
        </label>

        <div className="logo mobile-brand" aria-label={t('appHome')}>
          <img className="logo-mark" src={headerLogo} alt="" aria-hidden="true" />
          <b>Image Prompt Library</b>
        </div>

        <button className="iconbtn config-button" onClick={onConfig} aria-label={t('config')}>
          <Settings size={19} />
          {updateBadgeLabel && <span className="update-available-badge">{updateBadgeLabel}</span>}
        </button>
      </nav>

      <div className="status-row mobile-status-view-row">
        <div className="active-filter-strip" aria-label={t('currentFilters')}>
          <span className="template-count">{count} {t('referencesShown')}</span>
          <select className="sort-select" value={sort} onChange={event => onSort(event.currentTarget.value as ItemSortMode)} aria-label={t('sortChip')}>
            <option value="updated_desc">{t('sortByUpdated')}</option>
            <option value="created_desc">{t('sortByCreated')}</option>
            <option value="created_asc">{t('sortByOldest')}</option>
            <option value="title_asc">{t('sortByTitle')}</option>
            <option value="title_desc">{t('sortByTitleDesc')}</option>
            <option value="source_asc">{t('sortBySource')}</option>
            <option value="model_asc">{t('sortByModel')}</option>
          </select>
          {searchQuery && <span className="chip soft-chip">{t('searchChip')}: “{searchQuery}”</span>}
          {queryFilterChips.map(chip => <span key={chip} className="chip query-filter-chip">{chip}</span>)}
          {sortLabel && onClearSort && <button className="chip active-filter sort-chip" onClick={onClearSort}>{t('sortChip')}: {sortLabel} ×</button>}
          {clusterName && (
            <button className="chip active-filter" onClick={clearCluster}>
              {t('collectionChip')}: {clusterName} ×
            </button>
          )}
        </div>
        <div className="view-dock">
          <ViewToggle t={t} view={view} onView={onView} />
        </div>
      </div>
    </header>
  );
}
