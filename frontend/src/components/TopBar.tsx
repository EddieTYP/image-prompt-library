import { Filter, Search, Settings } from 'lucide-react';
import headerLogo from '../assets/header-logo.png';
import type { ViewMode } from '../types';
import type { Translator } from '../utils/i18n';
import ViewToggle from './ViewToggle';

interface Props {
  q: string;
  t: Translator;
  onQ: (v: string) => void;
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
  onQ,
  view,
  onView,
  onFilters,
  onConfig,
  count,
  clusterName,
  clearCluster,
}: Props) {
  return (
    <header className="chrome">
      <nav className="nav-row" aria-label={t('primaryNavigation')}>
        <button className="vista-button filter-button" onClick={onFilters}>
          <Filter size={18} />
          {t('filters')}
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

        <div className="logo" aria-label={t('appHome')}>
          <img className="logo-mark" src={headerLogo} alt="" aria-hidden="true" />
          <b>Image Prompt Library</b>
        </div>

        <button className="iconbtn" onClick={onConfig} aria-label={t('config')}>
          <Settings size={19} />
        </button>
      </nav>

      <div className="status-row">
        <div className="active-filter-strip" aria-label={t('currentFilters')}>
          <span className="template-count">{count} {t('referencesShown')}</span>
          {q && <span className="chip soft-chip">{t('searchChip')}: “{q}”</span>}
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
