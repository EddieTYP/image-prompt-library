import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api/client';
import type { AppConfig } from '../types';
import { PROMPT_LANGUAGE_LABELS, type PromptLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptLanguage[] = ['zh_hant', 'zh_hans', 'en'];
const GLOBAL_BUDGET_OPTIONS = [50, 75, 100, 150];
const FOCUS_BUDGET_OPTIONS = [24, 48, 72, 100];

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

      <section className="setting-group">
        <h3>Global thumbnail budget</h3>
        <p className="muted">Total real thumbnails shown across all cluster constellations.</p>
        <div className="segmented-control budget-control" aria-label="Global thumbnail budget">
          {GLOBAL_BUDGET_OPTIONS.map(budget => (
            <button key={budget} className={globalThumbnailBudget === budget ? 'active' : ''} onClick={() => onGlobalThumbnailBudget(budget)}>{budget}</button>
          ))}
        </div>
      </section>

      <section className="setting-group">
        <h3>Focus thumbnail budget</h3>
        <p className="muted">Maximum real thumbnails around the selected cluster card.</p>
        <div className="segmented-control budget-control" aria-label="Focus thumbnail budget">
          {FOCUS_BUDGET_OPTIONS.map(budget => (
            <button key={budget} className={focusThumbnailBudget === budget ? 'active' : ''} onClick={() => onFocusThumbnailBudget(budget)}>{budget}</button>
          ))}
        </div>
      </section>

      <p>Library path: <code>{cfg?.library_path}</code></p>
      <p>Database path: <code>{cfg?.database_path}</code></p>
    </aside>
  );
}
