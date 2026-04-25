import { Filter, Search, Settings, Sparkles } from 'lucide-react';
import type { ViewMode } from '../types';
import ViewToggle from './ViewToggle';

interface Props {
  q: string;
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
      <nav className="nav-row" aria-label="Primary">
        <button className="vista-button filter-button" onClick={onFilters}>
          <Filter size={18} />
          Filters
        </button>

        <label className="search toolbar-search" aria-label="Search all prompts">
          <Search size={20} />
          <input
            value={q}
            onChange={e => onQ(e.target.value)}
            placeholder="Search all prompts, titles, tags…"
            autoFocus
          />
        </label>

        <div className="logo" aria-label="Prompt Library home">
          <Sparkles size={22} />
          <div>
            <b>Prompt Library</b>
            <span>ChatGPT Image2 reference</span>
          </div>
        </div>

        <button className="iconbtn" onClick={onConfig} aria-label="Config">
          <Settings size={19} />
        </button>
      </nav>

      <div className="status-row">
        <div className="active-filter-strip" aria-label="Current filters">
          <span className="template-count">{count} references shown</span>
          {q && <span className="chip soft-chip">Search: “{q}”</span>}
          {clusterName && (
            <button className="chip active-filter" onClick={clearCluster}>
              Collection: {clusterName} ×
            </button>
          )}
        </div>
        <div className="view-dock">
          <ViewToggle view={view} onView={onView} />
        </div>
      </div>
    </header>
  );
}
