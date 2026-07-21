import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { X } from 'lucide-react';
import { api, isDemoMode } from '../api/client';
import type { AppConfig, AppUpdateStatus, CleanupPreview, CodexNativeAuthStart, GenerationProviderStatus } from '../types';
import { UI_LANGUAGE_LABELS, type Translator, type UiLanguage } from '../utils/i18n';
import { getPromptCopyLanguageLabel, type PromptCopyLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptCopyLanguage[] = ['origin', 'en', 'zh_hant', 'zh_hans'];
const UI_LANGUAGE_OPTIONS: UiLanguage[] = ['zh_hant', 'zh_hans', 'en'];

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
  focusProviders = false,
  t,
  onClose,
  uiLanguage,
  onUiLanguage,
  preferredLanguage,
  onPreferredLanguage,
  updateStatus,
  onRefreshUpdateStatus,
  onUpdateInstalled,
  onProvidersChanged = () => undefined,
  onLibraryCleanup = () => undefined,
}: {
  open: boolean;
  focusProviders?: boolean;
  t: Translator;
  onClose: () => void;
  uiLanguage: UiLanguage;
  onUiLanguage: (language: UiLanguage) => void;
  preferredLanguage: PromptCopyLanguage;
  onPreferredLanguage: (language: PromptCopyLanguage) => void;
  updateStatus?: AppUpdateStatus;
  onRefreshUpdateStatus: () => Promise<AppUpdateStatus | undefined>;
  onUpdateInstalled: (targetVersion: string, requiresManualRestart: boolean) => void;
  onProvidersChanged?: () => void;
  onLibraryCleanup?: () => void;
}) {
  const [cfg, setCfg] = useState<AppConfig>();
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreview>();
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string>();
  const [authStart, setAuthStart] = useState<CodexNativeAuthStart>();
  const [providerMessage, setProviderMessage] = useState<string>();
  const [providerBusy, setProviderBusy] = useState(false);
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<string>();
  const [updateInstalled, setUpdateInstalled] = useState<{ targetVersion: string; requiresManualRestart: boolean; message: string }>();
  const [showActiveUpdateConfirm, setShowActiveUpdateConfirm] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const providersSectionRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  const loadProviders = useCallback(() => api.generationProviders().then(nextProviders => {
    setProviders(nextProviders);
    onProvidersChanged();
  }).catch(() => {
    setProviders(providerFallback);
    setProviderMessage('Could not load provider status from the local backend. Showing safe local fallback.');
    onProvidersChanged();
  }), [onProvidersChanged]);

  const loadCleanupPreview = useCallback(async () => {
    if (isDemoMode) return;
    setCleanupBusy(true);
    setCleanupMessage(undefined);
    try {
      setCleanupPreview(await api.cleanupPreview());
    } catch (err) {
      setCleanupMessage(err instanceof Error ? err.message : 'Could not preview cleanup.');
    } finally {
      setCleanupBusy(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      api.config().then(setCfg).catch(() => undefined);
      onRefreshUpdateStatus().catch(() => undefined);
      loadProviders();
      if (!isDemoMode) void loadCleanupPreview();
    }
  }, [open, onRefreshUpdateStatus, loadProviders, loadCleanupPreview]);

  useEffect(() => {
    if (!open) return;
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement && !drawerRef.current?.contains(activeElement)) {
      openerRef.current = activeElement;
    }
    window.setTimeout(() => {
      if (focusProviders) {
        providersSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        providersSectionRef.current?.focus({ preventScroll: true });
      } else {
        closeButtonRef.current?.focus({ preventScroll: true });
      }
    }, 0);
  }, [open, focusProviders]);

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

  const activeUpdateJobs = (updateStatus?.active_generation_jobs.running || 0) + (updateStatus?.active_generation_jobs.queued || 0);
  const readyProviderCount = providers.filter(provider => provider.can_generate ?? Boolean(provider.available && provider.authenticated && provider.configured)).length;
  const generationSetupLabel = readyProviderCount > 0 ? `${readyProviderCount} ready` : 'Optional; not connected';
  const updateSetupLabel = updateStatus
    ? (updateStatus.error
      ? 'Could not check for updates'
      : updateStatus.update_capability === 'source'
        ? 'Managed outside app'
        : (updateStatus.update_available ? `Update available: ${updateStatus.latest_version}` : `Up to date: ${updateStatus.current_version}`))
    : 'Unavailable';
  const refreshUpdateStatus = () => onRefreshUpdateStatus().catch(() => {
    setUpdateMessage('Could not check app updates.');
    return undefined;
  });
  const beginUpdate = async (cancelActiveGenerationJobs: boolean) => {
    if (!updateStatus?.latest_version) return;
    setUpdateBusy(true);
    setUpdateMessage(undefined);
    try {
      const result = await api.startAppUpdate({ target_version: updateStatus.latest_version, cancel_active_generation_jobs: cancelActiveGenerationJobs });
      setShowActiveUpdateConfirm(false);
      setUpdateInstalled({ targetVersion: result.target_version, requiresManualRestart: result.requires_manual_restart, message: result.message });
      setUpdateMessage(undefined);
      await refreshUpdateStatus();
      onUpdateInstalled(result.target_version, result.requires_manual_restart);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not install update.';
      if (message.includes('active_generation_jobs')) setShowActiveUpdateConfirm(true);
      setUpdateMessage(message);
    } finally {
      setUpdateBusy(false);
    }
  };
  const requestUpdate = () => {
    if (activeUpdateJobs > 0) {
      setShowActiveUpdateConfirm(true);
      return;
    }
    void beginUpdate(false);
  };
  const restartInstruction = updateInstalled?.requiresManualRestart
    ? 'Stop the running Terminal server, then start Image Prompt Library again to use the new version.'
    : 'The update has been installed. The macOS service restart has been scheduled; reconnect after it comes back online.';
  const brokenImageCount = cleanupPreview?.broken_image_records.length || 0;
  const unreferencedFileCount = cleanupPreview?.unreferenced_files.length || 0;
  const cleanupHasWork = brokenImageCount > 0 || unreferencedFileCount > 0;
  const applyCleanup = async () => {
    if (!cleanupHasWork || !cleanupPreview) return;
    if (!confirm(`Clean up ${brokenImageCount} broken image records and ${unreferencedFileCount} unreferenced files?`)) return;
    setCleanupBusy(true);
    setCleanupMessage(undefined);
    try {
      const result = await api.applyCleanup({
        preview_token: cleanupPreview.preview_token,
        remove_broken_image_records: brokenImageCount > 0,
        remove_unreferenced_files: unreferencedFileCount > 0,
      });
      setCleanupPreview(result);
      setCleanupMessage(`Removed ${result.removed_broken_image_records} broken records and ${result.removed_unreferenced_files} files.`);
      onLibraryCleanup();
    } catch (err) {
      setCleanupMessage(err instanceof Error ? err.message : 'Could not apply cleanup.');
    } finally {
      setCleanupBusy(false);
    }
  };

  return (
    <aside
      ref={drawerRef}
      className={`config drawer ${open ? 'open' : ''}`}
      aria-label={t('config')}
      aria-hidden={!open}
      inert={!open}
      onKeyDown={handleKeyDown}
    >
      <div className="drawer-head">
        <h2>{t('config')}</h2>
        <button
          ref={closeButtonRef}
          className="panel-close"
          onClick={closePanel}
          aria-label={t('closeConfig')}
          tabIndex={open ? 0 : -1}
        >
          <X size={20} strokeWidth={2.25} />
        </button>
      </div>

      {!isDemoMode && (
        <section className="setting-group local-setup-section">
          <h3>{t('localSetup')}</h3>
          <p className="muted">{t('localSetupHelp')}</p>
          <dl className="local-setup-list">
            <div><dt>{t('appVersion')}</dt><dd><code>{cfg?.version || updateStatus?.current_version || 'unknown'}</code></dd></div>
            <div><dt>{t('libraryPath')}</dt><dd><code>{cfg?.library_path || 'unavailable'}</code></dd></div>
            <div><dt>{t('databasePath')}</dt><dd><code>{cfg?.database_path || 'unavailable'}</code></dd></div>
            <div><dt>{t('updateStatusLabel')}</dt><dd>{updateSetupLabel}</dd></div>
            <div><dt>{t('generationStatusLabel')}</dt><dd>{generationSetupLabel}</dd></div>
          </dl>
          <div className="local-setup-commands" aria-label={t('setupCommands')}>
            <p><span>{t('statusCommandHelp')}</span><code>image-prompt-library status</code></p>
            <p><span>{t('doctorCommandHelp')}</span><code>image-prompt-library doctor</code></p>
            <p><span>{t('firstRunSampleHelp')}</span><code>image-prompt-library sample-data en</code></p>
          </div>
        </section>
      )}

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

      <section className="setting-group app-update-section">
        <h3>App update</h3>
        {!updateStatus && <p className="muted">Checking for updates…</p>}
        {updateInstalled ? (
          <div className="update-card update-complete-card" role="status">
            <p className="update-kicker">Update installed</p>
            <p className="update-title">{updateInstalled.requiresManualRestart ? <>Restart required to finish updating to <code>{updateInstalled.targetVersion}</code>.</> : updateInstalled.message}</p>
            <p className="provider-help">{restartInstruction}</p>
            {updateInstalled.requiresManualRestart && <p className="update-command-hint"><code>image-prompt-library start</code></p>}
          </div>
        ) : updateStatus?.error ? (
          <p className="muted">Could not check for updates.</p>
        ) : updateStatus?.update_capability === 'source' ? (
          <p className="muted">This source checkout is managed outside the app. Update it with your development workflow.</p>
        ) : updateStatus?.update_capability === 'command_only' && updateStatus.update_available ? (
          <div className="update-card">
            <p className="muted"><strong>Update available</strong>: <code>{updateStatus.latest_version}</code></p>
            <p className="muted">Windows updates run from PowerShell. Use:</p>
            {updateStatus.update_command && <p className="update-command-hint"><code>{updateStatus.update_command}</code></p>}
            {updateStatus.release_url && <a className="secondary" href={updateStatus.release_url} target="_blank" rel="noreferrer">View release</a>}
          </div>
        ) : updateStatus && !updateStatus.update_available ? (
          <p className="muted">Image Prompt Library is up to date. Current version: <code>{updateStatus.current_version}</code></p>
        ) : updateStatus?.update_available && (
          <div className="update-card">
            <p className="muted"><strong>Update available</strong>: <code>{updateStatus.latest_version}</code></p>
            <p className="muted">Current version: <code>{updateStatus.current_version}</code></p>
            {showActiveUpdateConfirm ? (
              <div className="update-warning">
                <p>Updating requires restarting the app.</p>
                <p>There are {updateStatus.active_generation_jobs.running} generation jobs running and {updateStatus.active_generation_jobs.queued} queued. If you continue now, unfinished jobs will be cancelled and unfinished results will not be saved.</p>
                <div className="provider-actions">
                  <button className="secondary" onClick={() => setShowActiveUpdateConfirm(false)} disabled={updateBusy}>Update later</button>
                  <button className="danger" onClick={() => beginUpdate(true)} disabled={updateBusy}>Cancel jobs and update</button>
                </div>
              </div>
            ) : (
              <div className="provider-actions">
                <button className="primary" onClick={requestUpdate} disabled={updateBusy}>{updateBusy ? 'Installing…' : 'Update and restart'}</button>
                {updateStatus.release_url && <a className="secondary" href={updateStatus.release_url} target="_blank" rel="noreferrer">View release</a>}
              </div>
            )}
            <p className="provider-help">{updateStatus.requires_manual_restart ? 'This app is running from Terminal. After installation, stop the server and start it again to use the new version.' : 'This app is running as a macOS service. The updater can restart the service after installation.'}</p>
          </div>
        )}
        {updateMessage && <p className="provider-message">{updateMessage}</p>}
      </section>

      {!isDemoMode && (
        <section className="setting-group cleanup-section">
          <h3>Library cleanup</h3>
          <p className="muted">Local maintenance for missing image rows and unused media files.</p>
          <div className="cleanup-counts">
            <span><strong>{brokenImageCount}</strong> broken image records</span>
            <span><strong>{unreferencedFileCount}</strong> unreferenced files</span>
          </div>
          <div className="provider-actions">
            <button className="secondary" onClick={loadCleanupPreview} disabled={cleanupBusy}>{cleanupBusy ? 'Checking...' : 'Preview cleanup'}</button>
            <button className="danger" onClick={applyCleanup} disabled={cleanupBusy || !cleanupHasWork}>Apply cleanup</button>
          </div>
          {cleanupMessage && <p className="provider-message">{cleanupMessage}</p>}
        </section>
      )}

      <section ref={providersSectionRef} className="setting-group provider-section" tabIndex={-1} aria-labelledby="config-providers-title">
        <h3 id="config-providers-title">{t('providers')}</h3>
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
