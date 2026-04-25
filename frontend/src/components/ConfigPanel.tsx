import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api/client';
import type { AppConfig } from '../types';
import { PROMPT_LANGUAGE_LABELS, type PromptLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptLanguage[] = ['zh_hant', 'zh_hans', 'en'];
const GLOBAL_BUDGET_MIN = 50;
const GLOBAL_BUDGET_MAX = 150;
const GLOBAL_BUDGET_STEP = 5;
const FOCUS_BUDGET_MIN = 24;
const FOCUS_BUDGET_MAX = 100;
const FOCUS_BUDGET_STEP = 4;

export default function ConfigPanel({
  open,
  onClose,
  preferredLanguage,
  onPreferredLanguage,
  globalThumbnailBudget,
  onGlobalThumbnailBudget,
  focusThumbnailBudget,
  onFocusThumbnailBudget,
}: {
  open: boolean;
  onClose: () => void;
  preferredLanguage: PromptLanguage;
  onPreferredLanguage: (language: PromptLanguage) => void;
  globalThumbnailBudget: number;
  onGlobalThumbnailBudget: (budget: number) => void;
  focusThumbnailBudget: number;
  onFocusThumbnailBudget: (budget: number) => void;
}) {
  const [cfg, setCfg] = useState<AppConfig>();

  useEffect(() => {
    if (open) api.config().then(setCfg).catch(() => undefined);
  }, [open]);

  return (
    <aside className={`config drawer ${open ? 'open' : ''}`}>
      <div className="drawer-head">
        <h2>Config</h2>
        <button onClick={onClose} aria-label="Close config"><X /></button>
      </div>

      <section className="setting-group">
        <h3>Prompt copy language</h3>
        <p className="muted">Copy uses your preferred prompt first, then English, then any available prompt.</p>
        <div className="segmented-control" aria-label="Preferred prompt language">
          {LANGUAGE_OPTIONS.map(language => (
            <button
              key={language}
              className={preferredLanguage === language ? 'active' : ''}
              onClick={() => onPreferredLanguage(language)}
            >
              {PROMPT_LANGUAGE_LABELS[language]}
            </button>
          ))}
        </div>
      </section>

      <section className="setting-group range-setting">
        <div className="setting-title-row">
          <h3>Global thumbnails</h3>
          <strong>{globalThumbnailBudget}</strong>
        </div>
        <p className="muted">Overall Explore density across all clusters.</p>
        <input
          type="range"
          min={GLOBAL_BUDGET_MIN}
          max={GLOBAL_BUDGET_MAX}
          step={GLOBAL_BUDGET_STEP}
          value={globalThumbnailBudget}
          aria-label="Global thumbnail budget"
          onChange={event => onGlobalThumbnailBudget(Number(event.currentTarget.value))}
        />
        <div className="range-ticks"><span>Calm</span><span>Balanced</span><span>Dense</span></div>
      </section>

      <section className="setting-group range-setting">
        <div className="setting-title-row">
          <h3>Focus thumbnails</h3>
          <strong>{focusThumbnailBudget}</strong>
        </div>
        <p className="muted">Maximum real thumbnails around the selected cluster.</p>
        <input
          type="range"
          min={FOCUS_BUDGET_MIN}
          max={FOCUS_BUDGET_MAX}
          step={FOCUS_BUDGET_STEP}
          value={focusThumbnailBudget}
          aria-label="Focus thumbnail budget"
          onChange={event => onFocusThumbnailBudget(Number(event.currentTarget.value))}
        />
        <div className="range-ticks"><span>Compact</span><span>Gallery</span><span>Full</span></div>
      </section>

      <p>Library path: <code>{cfg?.library_path}</code></p>
      <p>Database path: <code>{cfg?.database_path}</code></p>
    </aside>
  );
}
