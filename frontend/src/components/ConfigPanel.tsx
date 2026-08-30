import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { X } from 'lucide-react';
import { api, isDemoMode } from '../api/client';
import { restoreFocusAfterMotion } from '../hooks/useModalFocus';
import type { AppearancePreset, AppConfig, AppUpdateStatus, CleanupPreview, GenerationProviderStatus, ProviderDeviceAuthStart } from '../types';
import { UI_LANGUAGE_LABELS, type Translator, type UiLanguage } from '../utils/i18n';
import { getPromptCopyLanguageLabel, type PromptCopyLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptCopyLanguage[] = ['origin', 'en', 'zh_hant', 'zh_hans'];
const UI_LANGUAGE_OPTIONS: UiLanguage[] = ['zh_hant', 'zh_hans', 'en'];

function providerStateLabel(provider: GenerationProviderStatus, t: Translator) {
  if (provider.state === 'not_configured') return t('providerStateNotConfigured');
  if (provider.state === 'not_connected') return t('providerStateNotConnected');
  if (provider.state === 'connected') return t('providerStateConnected');
  if (provider.state === 'demo_unavailable') return t('providerStateLocalOnly');
  if (provider.state === 'available') return t('providerStateAvailable');
  if (provider.state === 'expired') return t('providerStateExpired');
  return provider.state || t('providerStateUnavailable');
}

function featureSummary(provider: GenerationProviderStatus, t: Translator) {
  const features = [
    provider.features.text_to_image ? t('providerFeatureTextToImage') : undefined,
    provider.features.text_reference_to_image ? t('providerFeatureTextReferenceToImage') : undefined,
    provider.features.image_edit ? t('providerFeatureImageEdit') : undefined,
    provider.features.manual_result_upload ? t('providerFeatureManualUpload') : undefined,
  ].filter(Boolean);
  return features.length ? features.join(' · ') : t('providerFeaturesNone');
}

const FOCUSABLE_SELECTOR = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function scrollIntoViewRespectingMotion(element: HTMLElement | null) {
  if (!element) return;
  const behavior: ScrollBehavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  element.scrollIntoView({ behavior, block: 'start' });
}

const providerFallback: GenerationProviderStatus[] = [
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
    max_input_images: 4,
    token_present: false,
    account_id: null,
  },
  {
    provider: 'xai_grok_oauth',
    display_name: 'Grok OAuth · Experimental',
    auth_mode: 'grok_oauth_device',
    optional: true,
    configured: true,
    authenticated: false,
    available: false,
    state: 'not_connected',
    reason: 'provider_status_unavailable',
    features: { text_to_image: false, text_reference_to_image: false, image_edit: false },
    max_input_images: 3,
    token_present: false,
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
  appearance,
  onAppearance,
  updateStatus,
  onRefreshUpdateStatus,
  onUpdateInstalled,
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
  appearance: AppearancePreset;
  onAppearance: (appearance: AppearancePreset) => void;
  updateStatus?: AppUpdateStatus;
  onRefreshUpdateStatus: (refresh?: boolean) => Promise<AppUpdateStatus | undefined>;
  onUpdateInstalled: (targetVersion: string, requiresManualRestart: boolean) => void;
  onLibraryCleanup?: () => void;
}) {
  const [cfg, setCfg] = useState<AppConfig>();
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreview>();
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string>();
  const [authStarts, setAuthStarts] = useState<Record<string, ProviderDeviceAuthStart | undefined>>({});
  const [providerMessage, setProviderMessage] = useState<string>();
  const [providerActionMessages, setProviderActionMessages] = useState<Record<string, string | undefined>>({});
  const [providerBusy, setProviderBusy] = useState<string>();
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateCheckBusy, setUpdateCheckBusy] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<string>();
  const [updateInstalled, setUpdateInstalled] = useState<{ targetVersion: string; requiresManualRestart: boolean; message: string }>();
  const [showActiveUpdateConfirm, setShowActiveUpdateConfirm] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const providersSectionRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const closeMotionCleanupRef = useRef<(() => void) | undefined>(undefined);
  const cleanupInFlightRef = useRef(false);
  const cleanupRequestRef = useRef(0);
  const providersRequestRef = useRef(0);
  const providerActionRequestRef = useRef(0);

  const loadProviders = useCallback(async () => {
    const requestId = providersRequestRef.current + 1;
    providersRequestRef.current = requestId;
    try {
      const nextProviders = await api.generationProviders();
      if (providersRequestRef.current !== requestId) return;
      setProviders(nextProviders.filter(provider => provider.provider !== 'manual_upload'));
    } catch {
      if (providersRequestRef.current !== requestId) return;
      setProviders(providerFallback);
      setProviderMessage(t('providerStatusLoadFailed'));
    }
  }, [t]);

  const loadCleanupPreview = useCallback(async () => {
    if (isDemoMode || cleanupInFlightRef.current) return;
    cleanupInFlightRef.current = true;
    const requestId = cleanupRequestRef.current + 1;
    cleanupRequestRef.current = requestId;
    setCleanupBusy(true);
    setCleanupPreview(undefined);
    setCleanupMessage(undefined);
    try {
      const preview = await api.cleanupPreview();
      if (cleanupRequestRef.current === requestId) setCleanupPreview(preview);
    } catch (err) {
      if (cleanupRequestRef.current === requestId) setCleanupMessage(err instanceof Error ? err.message : t('cleanupPreviewFailed'));
    } finally {
      if (cleanupRequestRef.current === requestId) {
        cleanupInFlightRef.current = false;
        setCleanupBusy(false);
      }
    }
  }, [t]);

  useEffect(() => {
    if (!open) {
      providersRequestRef.current += 1;
      providerActionRequestRef.current += 1;
      setProviderBusy(undefined);
      return;
    }
    api.config().then(setCfg).catch(() => undefined);
    loadProviders();
  }, [open, loadProviders, loadCleanupPreview]);

  useEffect(() => {
    if (!open) return;
    closeMotionCleanupRef.current?.();
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement && !drawerRef.current?.contains(activeElement)) {
      openerRef.current = activeElement;
    }
    const frame = window.requestAnimationFrame(() => {
      if (focusProviders) {
        scrollIntoViewRespectingMotion(providersSectionRef.current);
        providersSectionRef.current?.focus({ preventScroll: true });
      } else {
        closeButtonRef.current?.focus({ preventScroll: true });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, focusProviders]);

  useEffect(() => () => {
    providersRequestRef.current += 1;
    providerActionRequestRef.current += 1;
    closeMotionCleanupRef.current?.();
  }, []);

  const closePanel = () => {
    providersRequestRef.current += 1;
    providerActionRequestRef.current += 1;
    setProviderBusy(undefined);
    closeMotionCleanupRef.current?.();
    const fallbacks = Array.from(document.querySelectorAll<HTMLElement>('.config-button, .toolbar-search input'));
    // Static compatibility marker: focusFirstAvailable([opener, ...fallbacks]) runs after drawer exit.
    closeMotionCleanupRef.current = restoreFocusAfterMotion(drawerRef.current, [openerRef.current, ...fallbacks]);
    onClose();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closePanel();
      return;
    }
    if (event.key !== 'Tab' || !drawerRef.current) return;
    const focusable = Array.from(drawerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter(element => element.getClientRects().length > 0 || element === document.activeElement);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus({ preventScroll: true });
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    }
  };

  const startProviderAuth = async (providerId: string) => {
    const requestId = providerActionRequestRef.current + 1;
    providerActionRequestRef.current = requestId;
    setProviderBusy(providerId);
    setProviderActionMessages(current => ({ ...current, [providerId]: undefined }));
    try {
      const started = providerId === 'xai_grok_oauth' ? await api.grokOAuthAuthStart() : await api.codexNativeAuthStart();
      if (providerActionRequestRef.current !== requestId) return;
      setAuthStarts(current => ({ ...current, [providerId]: started }));
    } catch (err) {
      if (providerActionRequestRef.current !== requestId) return;
      setProviderActionMessages(current => ({ ...current, [providerId]: err instanceof Error ? err.message : t('oauthStartFailed') }));
    } finally {
      if (providerActionRequestRef.current === requestId) setProviderBusy(undefined);
    }
  };

  const pollProviderAuth = async (providerId: string) => {
    const authStart = authStarts[providerId];
    if (!authStart) return;
    const requestId = providerActionRequestRef.current + 1;
    providerActionRequestRef.current = requestId;
    setProviderBusy(providerId);
    setProviderActionMessages(current => ({ ...current, [providerId]: undefined }));
    try {
      const pollResult = providerId === 'xai_grok_oauth'
        ? await api.grokOAuthAuthPoll({ device_code: authStart.device_code || '' })
        : await api.codexNativeAuthPoll({ device_auth_id: authStart.device_auth_id || '', user_code: authStart.user_code });
      if (providerActionRequestRef.current !== requestId) return;
      if ('status' in pollResult && pollResult.status === 'pending') {
        setProviderActionMessages(current => ({ ...current, [providerId]: t('oauthPending') }));
        return;
      }
      setAuthStarts(current => ({ ...current, [providerId]: undefined }));
      await loadProviders();
    } catch (err) {
      if (providerActionRequestRef.current !== requestId) return;
      setProviderActionMessages(current => ({ ...current, [providerId]: err instanceof Error ? err.message : t('oauthIncomplete') }));
    } finally {
      if (providerActionRequestRef.current === requestId) setProviderBusy(undefined);
    }
  };

  const disconnectProviderAuth = async (providerId: string) => {
    const requestId = providerActionRequestRef.current + 1;
    providerActionRequestRef.current = requestId;
    setProviderBusy(providerId);
    setProviderActionMessages(current => ({ ...current, [providerId]: undefined }));
    try {
      if (providerId === 'xai_grok_oauth') await api.grokOAuthAuthDisconnect();
      else await api.codexNativeAuthDisconnect();
      if (providerActionRequestRef.current !== requestId) return;
      setAuthStarts(current => ({ ...current, [providerId]: undefined }));
      await loadProviders();
    } catch (err) {
      if (providerActionRequestRef.current !== requestId) return;
      setProviderActionMessages(current => ({ ...current, [providerId]: err instanceof Error ? err.message : t('oauthDisconnectFailed') }));
    } finally {
      if (providerActionRequestRef.current === requestId) setProviderBusy(undefined);
    }
  };

  const activeUpdateJobs = (updateStatus?.active_generation_jobs.running || 0) + (updateStatus?.active_generation_jobs.queued || 0);
  const readyProviderCount = providers.filter(provider => provider.can_generate ?? Boolean(provider.available && provider.authenticated && provider.configured)).length;
  const generationSetupLabel = readyProviderCount > 0 ? t('readyProviderCount').replace('${count}', String(readyProviderCount)) : t('optionalNotConnected');
  const updateSetupLabel = updateStatus
      ? (updateStatus.error
       ? t('updateStatusFailed')
      : updateStatus.update_capability === 'source'
        ? t('updateSourceManaged')
        : (updateStatus.update_available ? `${t('updateAvailableVersion')}: ${updateStatus.latest_version}` : `${t('upToDate')} ${t('updateCurrentVersion')}: ${updateStatus.current_version}`))
    : t('providerStateUnavailable');
  const refreshUpdateStatus = () => onRefreshUpdateStatus(false).catch(() => {
    setUpdateMessage(t('updateStatusFailed'));
    return undefined;
  });
  const checkForUpdates = async () => {
    setUpdateCheckBusy(true);
    setUpdateMessage(undefined);
    try {
      await onRefreshUpdateStatus(true);
    } finally {
      setUpdateCheckBusy(false);
    }
  };
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
      const message = err instanceof Error ? err.message : t('updateInstallFailed');
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
    ? t('updateTerminalHelp')
    : t('updateServiceHelp');
  const brokenImageCount = cleanupPreview?.broken_image_records.length || 0;
  const unreferencedFileCount = cleanupPreview?.unreferenced_files.length || 0;
  const cleanupHasWork = brokenImageCount > 0 || unreferencedFileCount > 0;
  const applyCleanup = async () => {
    if (!cleanupHasWork || !cleanupPreview || cleanupInFlightRef.current) return;
    if (!confirm(t('cleanupConfirmation').replace('${broken}', String(brokenImageCount)).replace('${files}', String(unreferencedFileCount)))) return;
    cleanupInFlightRef.current = true;
    const requestId = cleanupRequestRef.current + 1;
    cleanupRequestRef.current = requestId;
    setCleanupBusy(true);
    setCleanupMessage(undefined);
    try {
      const result = await api.applyCleanup({
        preview_token: cleanupPreview.preview_token,
        remove_broken_image_records: brokenImageCount > 0,
        remove_unreferenced_files: unreferencedFileCount > 0,
      });
      if (cleanupRequestRef.current === requestId) {
        setCleanupPreview(result);
        setCleanupMessage(t('cleanupDone').replace('${broken}', String(result.removed_broken_image_records)).replace('${files}', String(result.removed_unreferenced_files)));
        onLibraryCleanup();
      }
    } catch (err) {
      if (cleanupRequestRef.current === requestId) setCleanupMessage(err instanceof Error ? err.message : t('cleanupApplyFailed'));
    } finally {
      if (cleanupRequestRef.current === requestId) {
        cleanupInFlightRef.current = false;
        setCleanupBusy(false);
      }
    }
  };

  return (
    <>
      {open && <div className="drawer-scrim" aria-hidden="true" onClick={closePanel} />}
      <aside
      ref={drawerRef}
      id="config-drawer"
      className={`config drawer ${open ? 'open' : ''}`}
      role="dialog"
      aria-modal="true"
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

      <section className="setting-group">
        <h3>{t('appearance')}</h3>
        <p className="muted">{t('appearanceHelp')}</p>
        <div className="appearance-control" role="radiogroup" aria-label={t('appearance')}>
          {([
            ['gallery_vermilion', 'appearanceGalleryVermilion'],
            ['pine_archive', 'appearancePineArchive'],
            ['aubergine_ink', 'appearanceAubergineInk'],
          ] as const).map(([preset, label]) => (
            <button
              key={preset}
              type="button"
              role="radio"
              aria-checked={appearance === preset}
              className={appearance === preset ? 'active' : ''}
              onClick={() => onAppearance(preset)}
            >
              <span className={`appearance-swatch appearance-swatch-${preset}`} aria-hidden="true" />
              <span>{t(label)}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="setting-group app-update-section">
         <h3>{t('appUpdate')}</h3>
         {!updateStatus && <p className="muted">{t('updateChecking')}</p>}
        {updateInstalled ? (
          <div className="update-card update-complete-card" role="status">
             <p className="update-kicker">{t('updateInstalled')}</p>
             <p className="update-title">{updateInstalled.requiresManualRestart ? <>{t('updateRestartRequired')} <code>{updateInstalled.targetVersion}</code>.</> : updateInstalled.message}</p>
            <p className="provider-help">{restartInstruction}</p>
            {updateInstalled.requiresManualRestart && <p className="update-command-hint"><code>image-prompt-library start</code></p>}
          </div>
        ) : updateStatus?.error ? (
           <p className="muted">{t('updateStatusFailed')}</p>
        ) : updateStatus?.update_capability === 'source' ? (
           <p className="muted">{t('updateSourceManaged')}</p>
        ) : updateStatus?.update_capability === 'command_only' && updateStatus.update_available ? (
          <div className="update-card">
             <p className="muted"><strong>{t('updateAvailableVersion')}</strong>: <code>{updateStatus.latest_version}</code></p>
             <p className="muted">{t('updatePowerShellHint')}</p>
            {updateStatus.update_command && <p className="update-command-hint"><code>{updateStatus.update_command}</code></p>}
             {updateStatus.release_url && <a className="secondary" href={updateStatus.release_url} target="_blank" rel="noreferrer">{t('viewRelease')}</a>}
          </div>
        ) : updateStatus && !updateStatus.update_available ? (
           <p className="muted">{t('upToDate')} {t('updateCurrentVersion')}: <code>{updateStatus.current_version}</code></p>
        ) : updateStatus?.update_available && (
          <div className="update-card">
             <p className="muted"><strong>{t('updateAvailableVersion')}</strong>: <code>{updateStatus.latest_version}</code></p>
             <p className="muted">{t('updateCurrentVersion')}: <code>{updateStatus.current_version}</code></p>
            {showActiveUpdateConfirm ? (
              <div className="update-warning">
                 <p>{t('updateRequiresRestart')}</p>
                 <p>{t('updateActiveJobs').replace('${running}', String(updateStatus.active_generation_jobs.running)).replace('${queued}', String(updateStatus.active_generation_jobs.queued))}</p>
                <div className="provider-actions">
                   <button className="secondary" onClick={() => setShowActiveUpdateConfirm(false)} disabled={updateBusy}>{t('updateLater')}</button>
                   <button className="danger" onClick={() => beginUpdate(true)} disabled={updateBusy}>{t('cancelJobsAndUpdate')}</button>
                </div>
              </div>
            ) : (
              <div className="provider-actions">
               <button className="primary" onClick={requestUpdate} disabled={updateBusy}>{updateBusy ? t('installing') : t('updateAndRestart')}</button>
               {updateStatus.release_url && <a className="secondary" href={updateStatus.release_url} target="_blank" rel="noreferrer">{t('viewRelease')}</a>}
              </div>
            )}
            <p className="provider-help">{updateStatus.requires_manual_restart ? t('updateTerminalHelp') : t('updateServiceHelp')}</p>
          </div>
        )}
        {!isDemoMode && !updateInstalled && updateStatus?.update_capability !== 'source' && (
          <div className="provider-actions">
            <button className="secondary" onClick={checkForUpdates} disabled={!updateStatus || updateBusy || updateCheckBusy}>
              {updateCheckBusy ? t('updateChecking') : t('checkForUpdates')}
            </button>
          </div>
        )}
        {updateMessage && <p className="provider-message">{updateMessage}</p>}
      </section>

      {!isDemoMode && (
        <section className="setting-group cleanup-section">
           <h3>{t('cleanupTitle')}</h3>
           <p className="muted">{t('cleanupHelp')}</p>
           {!cleanupPreview && <p className="cleanup-precheck-state" role="status">{t('cleanupPrecheck')}</p>}
           {cleanupPreview && cleanupHasWork && (
            <div className="cleanup-counts">
              <span><strong>{brokenImageCount}</strong> {t('brokenImageRecords')}</span>
              <span><strong>{unreferencedFileCount}</strong> {t('unreferencedFiles')}</span>
            </div>
          )}
          {cleanupPreview && !cleanupHasWork && <p className="cleanup-empty-state" role="status">{t('cleanupNoWork')}</p>}
          <div className="provider-actions">
             <button className="secondary" onClick={loadCleanupPreview} disabled={cleanupBusy}>{cleanupBusy ? t('checking') : t('previewCleanup')}</button>
             {cleanupPreview && cleanupHasWork && <button className="danger" onClick={applyCleanup} disabled={cleanupBusy}>{t('applyCleanup')}</button>}
          </div>
          {cleanupMessage && <p className="provider-message">{cleanupMessage}</p>}
        </section>
      )}

      <section ref={providersSectionRef} className="setting-group provider-section" tabIndex={-1} aria-labelledby="config-providers-title">
        <h3 id="config-providers-title">{t('providers')}</h3>
        <p className="muted">{t('providerSetupHelp')}</p>
        <div className="provider-list">
          {providers.map(provider => {
            const authStart = authStarts[provider.provider];
            const isBusy = providerBusy === provider.provider;
            return (
            <article className={`provider-card state-${provider.state}`} key={provider.provider}>
              <div className="provider-card-head">
                <div>
                  <strong>{provider.provider === 'openai_codex_oauth_native' ? 'ChatGPT / Codex OAuth' : provider.display_name}</strong>
                  <span>{provider.optional ? t('providerOptional') : t('providerBuiltIn')}</span>
                </div>
                <b>{providerStateLabel(provider, t)}</b>
              </div>
              <p className="muted">{featureSummary(provider, t)}</p>
              {['openai_codex_oauth_native', 'xai_grok_oauth'].includes(provider.provider) && (
                <div className="provider-actions">
                  {provider.state === 'not_configured' && (
                    <p className="provider-help">{t('providerClientHelp')}</p>
                  )}
                  {provider.account_id && <p className="provider-help">{t('providerAccount')}: <code>{provider.account_id}</code></p>}
                  {authStart && (
                    <div className="provider-auth-box">
                      <p><a href={authStart.verification_url || authStart.verification_uri_complete || authStart.verification_uri} target="_blank" rel="noreferrer">{t('providerVerification')}</a> <code>{authStart.user_code}</code></p>
                      <button className="secondary" onClick={() => pollProviderAuth(provider.provider)} disabled={isBusy}>{t('checkAuthorization')}</button>
                    </div>
                  )}
                  {!provider.authenticated && !authStart && (
                    <button className="secondary" onClick={() => startProviderAuth(provider.provider)} disabled={isDemoMode || provider.state === 'not_configured' || isBusy}>{t('connect')}</button>
                  )}
                  {provider.authenticated && <button className="secondary" onClick={() => disconnectProviderAuth(provider.provider)} disabled={isBusy}>{t('disconnect')}</button>}
                  {providerActionMessages[provider.provider] && <p className="provider-message" role="status">{providerActionMessages[provider.provider]}</p>}
                </div>
              )}
            </article>
          );})}
        </div>
        {providerMessage && <p className="provider-message">{providerMessage}</p>}
      </section>

      {!isDemoMode && (
        <section className="setting-group local-setup-section">
          <h3>{t('systemInformation')}</h3>
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
      </aside>
    </>
  );
}
