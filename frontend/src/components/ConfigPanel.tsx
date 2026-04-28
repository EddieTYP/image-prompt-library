import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api, isDemoMode } from '../api/client';
import type { AppConfig, CodexNativeAuthStart, GenerationProviderStatus } from '../types';
import { UI_LANGUAGE_LABELS, type Translator, type UiLanguage } from '../utils/i18n';
import { getPromptCopyLanguageLabel, type PromptCopyLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptCopyLanguage[] = ['origin', 'en', 'zh_hant', 'zh_hans'];
const UI_LANGUAGE_OPTIONS: UiLanguage[] = ['zh_hant', 'zh_hans', 'en'];
const GLOBAL_BUDGET_MIN = 50;
const GLOBAL_BUDGET_MAX = 150;
const GLOBAL_BUDGET_STEP = 5;
const FOCUS_BUDGET_MIN = 24;
const FOCUS_BUDGET_MAX = 100;
const FOCUS_BUDGET_STEP = 4;

function providerStateLabel(provider: GenerationProviderStatus) {
  if (provider.state === 'not_configured') return 'Not configured';
  if (provider.state === 'not_connected') return 'Not connected';
  if (provider.state === 'connected') return 'Connected';
  if (provider.state === 'demo_unavailable') return 'Local only';
  if (provider.state === 'available') return 'Available';
  if (provider.state === 'expired') return 'Expired';
  return provider.state || 'Unavailable';
}

function featureSummary(provider: GenerationProviderStatus) {
  const features = [
    provider.features.text_to_image ? 'Text→Image' : undefined,
    provider.features.text_reference_to_image ? 'Text+Reference→Image' : undefined,
    provider.features.image_edit ? 'Image edit' : undefined,
    provider.features.manual_result_upload ? 'Manual upload' : undefined,
  ].filter(Boolean);
  return features.length ? features.join(' · ') : 'No generation features enabled';
}

const providerFallback: GenerationProviderStatus[] = [
  {
    provider: 'manual_upload',
    display_name: 'Manual upload',
    optional: false,
    configured: true,
    authenticated: true,
    available: true,
    state: 'available',
    reason: null,
    features: { manual_result_upload: true },
  },
  {
    provider: 'openai_codex_oauth_native',
    display_name: 'ChatGPT / Codex OAuth',
    auth_mode: 'codex_oauth_native',
    optional: true,
    configured: false,
    authenticated: false,
    available: false,
    state: 'not_configured',
    reason: 'provider_status_unavailable',
    features: { text_to_image: false, text_reference_to_image: false, image_edit: false },
    token_present: false,
    account_id: null,
  },
];

export default function ConfigPanel({
  open,
  t,
  onClose,
  uiLanguage,
  onUiLanguage,
  preferredLanguage,
  onPreferredLanguage,
  globalThumbnailBudget,
  onGlobalThumbnailBudget,
  focusThumbnailBudget,
  onFocusThumbnailBudget,
}: {
  open: boolean;
  t: Translator;
  onClose: () => void;
  uiLanguage: UiLanguage;
  onUiLanguage: (language: UiLanguage) => void;
  preferredLanguage: PromptCopyLanguage;
  onPreferredLanguage: (language: PromptCopyLanguage) => void;
  globalThumbnailBudget: number;
  onGlobalThumbnailBudget: (budget: number) => void;
  focusThumbnailBudget: number;
  onFocusThumbnailBudget: (budget: number) => void;
}) {
  const [cfg, setCfg] = useState<AppConfig>();
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [authStart, setAuthStart] = useState<CodexNativeAuthStart>();
  const [providerMessage, setProviderMessage] = useState<string>();
  const [providerBusy, setProviderBusy] = useState(false);

  const loadProviders = () => api.generationProviders().then(setProviders).catch(() => {
    setProviders(providerFallback);
    setProviderMessage('Could not load provider status from the local backend. Showing safe local fallback.');
  });

  useEffect(() => {
    if (open) {
      api.config().then(setCfg).catch(() => undefined);
      loadProviders();
    }
  }, [open]);

  const startCodexAuth = async () => {
    setProviderBusy(true);
    setProviderMessage(undefined);
    try {
      const started = await api.codexNativeAuthStart();
      setAuthStart(started);
    } catch (err) {
      setProviderMessage(err instanceof Error ? err.message : 'Could not start OAuth.');
    } finally {
      setProviderBusy(false);
    }
  };

  const pollCodexAuth = async () => {
    if (!authStart) return;
    setProviderBusy(true);
    setProviderMessage(undefined);
    try {
      const pollResult = await api.codexNativeAuthPoll({ device_auth_id: authStart.device_auth_id, user_code: authStart.user_code });
      if ('status' in pollResult && pollResult.status === 'pending') {
        setProviderMessage('Authorization is still pending. Complete the browser approval, then check again.');
        return;
      }
      setAuthStart(undefined);
      await loadProviders();
    } catch (err) {
      setProviderMessage(err instanceof Error ? err.message : 'Authorization is not complete yet.');
    } finally {
      setProviderBusy(false);
    }
  };

  const disconnectCodexAuth = async () => {
    setProviderBusy(true);
    setProviderMessage(undefined);
    try {
      await api.codexNativeAuthDisconnect();
      setAuthStart(undefined);
      await loadProviders();
    } catch (err) {
      setProviderMessage(err instanceof Error ? err.message : 'Could not disconnect provider.');
    } finally {
      setProviderBusy(false);
    }
  };

  return (
    <aside className={`config drawer ${open ? 'open' : ''}`}>
      <div className="drawer-head">
        <h2>{t('config')}</h2>
        <button className="panel-close" onClick={onClose} aria-label={t('closeConfig')}><X size={18} /></button>
      </div>

      <section className="setting-group">
        <h3>{t('uiLanguage')}</h3>
        <div className="segmented-control" aria-label={t('uiLanguage')}>
          {UI_LANGUAGE_OPTIONS.map(language => (
            <button
              key={language}
              className={uiLanguage === language ? 'active' : ''}
              onClick={() => onUiLanguage(language)}
            >
              {UI_LANGUAGE_LABELS[language]}
            </button>
          ))}
        </div>
      </section>

      <section className="setting-group">
        <h3>{t('promptCopyLanguage')}</h3>
        <p className="muted">{t('promptCopyLanguageHelp')}</p>
        <div className="segmented-control prompt-copy-language-control" aria-label={t('preferredPromptLanguage')}>
          {LANGUAGE_OPTIONS.map(language => (
            <button
              key={language}
              className={preferredLanguage === language ? 'active' : ''}
              onClick={() => onPreferredLanguage(language)}
            >
              {getPromptCopyLanguageLabel(language, uiLanguage)}
            </button>
          ))}
        </div>
      </section>

      <section className="setting-group range-setting">
        <div className="setting-title-row">
          <h3>{t('globalThumbnails')}</h3>
          <strong>{globalThumbnailBudget}</strong>
        </div>
        <p className="muted">{t('globalThumbnailsHelp')}</p>
        <input
          type="range"
          min={GLOBAL_BUDGET_MIN}
          max={GLOBAL_BUDGET_MAX}
          step={GLOBAL_BUDGET_STEP}
          value={globalThumbnailBudget}
          aria-label={t('globalThumbnailBudget')}
          onChange={event => onGlobalThumbnailBudget(Number(event.currentTarget.value))}
        />
        <div className="range-ticks"><span>{t('calm')}</span><span>{t('balanced')}</span><span>{t('dense')}</span></div>
      </section>

      <section className="setting-group range-setting">
        <div className="setting-title-row">
          <h3>{t('focusThumbnails')}</h3>
          <strong>{focusThumbnailBudget}</strong>
        </div>
        <p className="muted">{t('focusThumbnailsHelp')}</p>
        <input
          type="range"
          min={FOCUS_BUDGET_MIN}
          max={FOCUS_BUDGET_MAX}
          step={FOCUS_BUDGET_STEP}
          value={focusThumbnailBudget}
          aria-label={t('focusThumbnailBudget')}
          onChange={event => onFocusThumbnailBudget(Number(event.currentTarget.value))}
        />
        <div className="range-ticks"><span>{t('compact')}</span><span>{t('gallery')}</span><span>{t('full')}</span></div>
      </section>

      <section className="setting-group provider-section">
        <h3>{t('providers')}</h3>
        <p className="muted">Generation providers are optional. The core library remains usable without OAuth.</p>
        <div className="provider-list">
          {providers.map(provider => (
            <article className={`provider-card state-${provider.state}`} key={provider.provider}>
              <div className="provider-card-head">
                <div>
                  <strong>{provider.provider === 'openai_codex_oauth_native' ? 'ChatGPT / Codex OAuth' : provider.display_name}</strong>
                  <span>{provider.optional ? 'Optional provider' : 'Built in'}</span>
                </div>
                <b>{providerStateLabel(provider)}</b>
              </div>
              <p className="muted">{featureSummary(provider)}</p>
              {provider.provider === 'openai_codex_oauth_native' && (
                <div className="provider-actions">
                  {provider.state === 'not_configured' && (
                    <p className="provider-help">Set IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID or ~/.image-prompt-library/config.json locally to enable Connect.</p>
                  )}
                  {provider.account_id && <p className="provider-help">Account: <code>{provider.account_id}</code></p>}
                  {authStart && (
                    <div className="provider-auth-box">
                      <p>Open <a href={authStart.verification_url || authStart.verification_uri_complete || authStart.verification_uri} target="_blank" rel="noreferrer">verification_url</a> and enter code <code>user_code: {authStart.user_code}</code>.</p>
                      <button className="secondary" onClick={pollCodexAuth} disabled={providerBusy}>Check authorization</button>
                    </div>
                  )}
                  {!provider.authenticated && !authStart && (
                    <button className="secondary" onClick={startCodexAuth} disabled={isDemoMode || provider.state === 'not_configured' || providerBusy}>Connect</button>
                  )}
                  {provider.authenticated && <button className="secondary" onClick={disconnectCodexAuth} disabled={providerBusy}>Disconnect</button>}
                </div>
              )}
            </article>
          ))}
        </div>
        {providerMessage && <p className="provider-message">{providerMessage}</p>}
      </section>

      <p>{t('libraryPath')}: <code>{cfg?.library_path}</code></p>
      <p>{t('databasePath')}: <code>{cfg?.database_path}</code></p>
    </aside>
  );
}
