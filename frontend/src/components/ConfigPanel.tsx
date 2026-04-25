import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api/client';
import type { AppConfig } from '../types';
import { PROMPT_LANGUAGE_LABELS, type PromptLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptLanguage[] = ['zh_hant', 'zh_hans', 'en'];

export default function ConfigPanel({
  open,
  onClose,
  preferredLanguage,
  onPreferredLanguage,
}: {
  open: boolean;
  onClose: () => void;
  preferredLanguage: PromptLanguage;
  onPreferredLanguage: (language: PromptLanguage) => void;
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

      <p>Library path: <code>{cfg?.library_path}</code></p>
      <p>Database path: <code>{cfg?.database_path}</code></p>
    </aside>
  );
}
