import { Filter, Settings, Search, Sparkles } from 'lucide-react';
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

      <section className="hero-shell" aria-label="Library search">
        <p className="eyebrow">Local creative reference library</p>
        <div className="hero-copy">
          <h1>Start your visual prompt collection</h1>
          <p>
            Browse beautiful AI image references, compare Chinese and English prompts,
            and turn saved generations into reusable inspiration.
          </p>
        </div>
        <label className="search hero-search">
          <Search size={21} />
          <input
            value={q}
            onChange={e => onQ(e.target.value)}
            placeholder="Search all prompts, titles, tags…"
            autoFocus
          />
        </label>
        <div className="hero-meta">
          <span className="template-count">{count} visible prompts</span>
          {clusterName && (
            <button className="chip active-filter" onClick={clearCluster}>
              Cluster: {clusterName} ×
            </button>
          )}
          <ViewToggle view={view} onView={onView} />
        </div>
      </section>
    </header>
  );
}
