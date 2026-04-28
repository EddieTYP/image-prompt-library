import { useEffect, useMemo, useState } from 'react';
import { api, mediaUrl } from '../api/client';
import type { GenerationJobRecord, GenerationProviderStatus, ItemDetail } from '../types';
import type { Translator } from '../utils/i18n';
import { resolveOriginalPrompt, resolvePromptText, type PromptCopyLanguage } from '../utils/prompts';

function providerReady(provider: GenerationProviderStatus) {
  if (provider.provider === 'manual_upload') return true;
  return Boolean(provider.available && provider.authenticated && provider.configured);
}

function statusLabel(status: string) {
  if (status === 'queued') return 'Queued';
  if (status === 'running') return 'Running';
  if (status === 'succeeded') return 'Ready';
  if (status === 'accepted') return 'Accepted';
  if (status === 'discarded') return 'Discarded';
  if (status === 'failed') return 'Failed';
  return status;
}

function jobResultUrl(job: GenerationJobRecord) {
  return job.result_path ? mediaUrl(job.result_path) : '';
}

export default function GenerationPanel({
  item,
  preferredLanguage,
  onClose,
  onAccepted,
  t,
}: {
  item: ItemDetail;
  preferredLanguage: PromptCopyLanguage;
  onClose: () => void;
  onAccepted: (item?: ItemDetail, message?: string) => void;
  t: Translator;
}) {
  const originalPrompt = resolveOriginalPrompt(item.prompts);
  const defaultPromptLanguage = preferredLanguage === 'origin' ? (originalPrompt?.language || 'en') : preferredLanguage;
  const defaultPrompt = resolvePromptText(item.prompts, preferredLanguage, item.title);
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [provider, setProvider] = useState('manual_upload');
  const [promptText, setPromptText] = useState(defaultPrompt);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [activeJobId, setActiveJobId] = useState<string>();

  const activeJob = useMemo(() => jobs.find(job => job.id === activeJobId), [jobs, activeJobId]);
  const selectedProvider = providers.find(candidate => candidate.provider === provider);
  const primaryProviders = providers.filter(candidate => candidate.provider !== 'manual_upload');

  const refreshJobs = async () => {
    const result = await api.generationJobs({ limit: 100 });
    const nextJobs = result.jobs.filter(job => job.source_item_id === item.id);
    setJobs(nextJobs);
    if (!activeJobId && nextJobs[0]) setActiveJobId(nextJobs[0].id);
    return nextJobs;
  };

  useEffect(() => {
    let cancelled = false;
    api.generationProviders()
      .then(nextProviders => {
        if (cancelled) return;
        setProviders(nextProviders);
        const firstReady = nextProviders.find(nextProvider => nextProvider.provider !== 'manual_upload' && providerReady(nextProvider)) || nextProviders.find(providerReady) || nextProviders[0];
        if (firstReady) setProvider(firstReady.provider);
      })
      .catch(() => setProviders([{ provider: 'manual_upload', display_name: 'Manual upload', optional: false, configured: true, authenticated: true, available: true, state: 'available', reason: null, features: { manual_result_upload: true } }]));
    refreshJobs().catch(() => undefined);
    return () => { cancelled = true; };
  }, [item.id]);

  const createJob = async () => {
    setBusy(true);
    setMessage('');
    try {
      const created = await api.createGenerationJob({
        source_item_id: item.id,
        mode: 'text_to_image',
        provider,
        model: provider === 'openai_codex_oauth_native' ? 'gpt-image-2' : null,
        prompt_language: defaultPromptLanguage,
        prompt_text: defaultPrompt,
        edited_prompt_text: promptText.trim() === defaultPrompt.trim() ? null : promptText.trim(),
        reference_image_ids: [],
        parameters: {},
      });
      setJobs(current => [created, ...current.filter(job => job.id !== created.id)]);
      setActiveJobId(created.id);
      setMessage(provider === 'manual_upload' ? 'Job created. Upload a generated result when ready.' : 'Job created. Run it when the provider is connected.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create generation job.');
    } finally {
      setBusy(false);
    }
  };

  const runJob = async (job: GenerationJobRecord) => {
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('Generating image…');
    setJobs(current => current.map(candidate => candidate.id === job.id ? { ...candidate, status: 'running' } : candidate));
    try {
      const updated = await api.runGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setMessage(updated.status === 'succeeded' ? 'Generation result is ready for review.' : `Job ${updated.status}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not run generation job.');
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const uploadManualResult = async (job: GenerationJobRecord, file?: File) => {
    if (!file) return;
    setBusy(true);
    setMessage('');
    try {
      const updated = await api.uploadGenerationResult(job.id, file);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setMessage('Manual result uploaded. Review it before accepting.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not upload result.');
    } finally {
      setBusy(false);
    }
  };

  const acceptJob = async (job: GenerationJobRecord, mode: 'attach' | 'new-item' = 'attach') => {
    setBusy(true);
    setMessage('');
    try {
      const result = mode === 'new-item'
        ? await api.acceptGenerationJobAsNewItem(job.id)
        : await api.acceptGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === result.job.id ? result.job : candidate));
      const acceptedMessage = mode === 'new-item' ? 'New variant item created' : 'Image added to item';
      setMessage(acceptedMessage);
      onAccepted(result.item, acceptedMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not accept result.');
    } finally {
      setBusy(false);
    }
  };

  const discardJob = async (job: GenerationJobRecord) => {
    setBusy(true);
    setMessage('');
    try {
      const updated = await api.discardGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setMessage('Generation job discarded.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not discard job.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="generation-panel modal polished-modal" onClick={event => event.stopPropagation()} aria-label="Generation workflow">
        <div className="drawer-head generation-panel-head">
          <div>
            <p className="drawer-eyebrow">Generation</p>
            <h2>Generate variant</h2>
            <p className="muted">Create a GenerationJob from this prompt, then review the result before it enters the library.</p>
          </div>
          <button className="modal-icon-button close" onClick={onClose} aria-label={t('close')}>×</button>
        </div>

        <div className="generation-grid">
          <section className="generation-compose-card">
            <h3>Prompt</h3>
            <label>
              <span>Provider</span>
              <select value={provider} onChange={event => setProvider(event.currentTarget.value)}>
                {primaryProviders.map(nextProvider => (
                  <option key={nextProvider.provider} value={nextProvider.provider} disabled={!providerReady(nextProvider)}>
                    {nextProvider.display_name}{providerReady(nextProvider) ? '' : ' · unavailable'}
                  </option>
                ))}
                {primaryProviders.length === 0 && <option value="manual_upload">No connected image provider</option>}
                {!providers.some(nextProvider => nextProvider.provider === 'openai_codex_oauth_native') && <option value="openai_codex_oauth_native">ChatGPT / Codex OAuth</option>}
              </select>
            </label>
            {selectedProvider && !providerReady(selectedProvider) && (
              <p className="provider-help">This provider is not ready. Configure it in Providers before running generation.</p>
            )}
            <textarea value={promptText} onChange={event => setPromptText(event.currentTarget.value)} />
            <button className="primary" onClick={createJob} disabled={busy || !promptText.trim()}>Create GenerationJob</button>
            <details className="generation-advanced">
              <summary>Upload external result</summary>
              <p className="muted">Manual upload is kept as an advanced fallback for images generated outside the app.</p>
            </details>
          </section>

          <section className="generation-inbox-card">
            <div className="generation-inbox-head">
              <h3>Result inbox</h3>
              <button className="secondary" onClick={() => refreshJobs()} disabled={busy}>Refresh</button>
            </div>
            {jobs.length === 0 && <p className="muted">No generation jobs for this prompt yet.</p>}
            {jobs.map(job => (
              <article className={`generation-job-card status-${job.status} ${job.result_path ? 'has-result' : ''}`} key={job.id}>
                <header>
                  <strong>{job.provider === 'openai_codex_oauth_native' ? 'ChatGPT / Codex OAuth' : job.provider}</strong>
                  <b>{statusLabel(job.status)}</b>
                </header>
                <p className="muted">{job.edited_prompt_text || job.prompt_text}</p>
                {jobResultUrl(job) ? (
                  <img className="generation-result-image generation-result-fade-in" src={jobResultUrl(job)} alt="Generation result" />
                ) : job.status === 'running' ? (
                  <div className="generation-result-placeholder generation-shimmer">Generating image…</div>
                ) : (
                  <div className="generation-result-placeholder">No result image yet</div>
                )}
                {job.error && <p className="error">{job.error}</p>}
                <div className="generation-job-actions">
                  {job.provider === 'openai_codex_oauth_native' && ['queued', 'failed'].includes(job.status) && <button className="secondary" onClick={() => runJob(job)} disabled={busy}>{busy && activeJobId === job.id ? 'Generating…' : 'Run'}</button>}
                  {job.provider === 'manual_upload' && !job.result_path && !['accepted', 'discarded'].includes(job.status) && (
                    <details className="generation-advanced inline-upload">
                      <summary>Upload external result</summary>
                      <label className="secondary file-button">Choose image<input type="file" accept="image/*" onChange={event => uploadManualResult(job, event.currentTarget.files?.[0])} /></label>
                    </details>
                  )}
                  {job.status === 'succeeded' && (
                    <span className="accept-dropdown">
                      <button className="primary" onClick={() => acceptJob(job, 'attach')} disabled={busy}>Attach to current item</button>
                      <button className="secondary" onClick={() => acceptJob(job, 'new-item')} disabled={busy}>Save as new item</button>
                    </span>
                  )}
                  {!['accepted', 'discarded'].includes(job.status) && <button className="secondary" onClick={() => discardJob(job)} disabled={busy}>Discard</button>}
                </div>
              </article>
            ))}
          </section>
        </div>
        {activeJob && <p className="muted">Selected job: <code>{activeJob.id}</code></p>}
        {message && <p className="provider-message">{message}</p>}
      </section>
    </div>
  );
}
