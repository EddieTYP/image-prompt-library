import { useEffect, useMemo, useRef, useState } from 'react';
import { api, mediaUrl } from '../api/client';
import type { GenerationJobAcceptAsNewItemPayload, GenerationJobRecord, GenerationProviderStatus, ItemDetail } from '../types';
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

function friendlyFailure(job: GenerationJobRecord) {
  const rawKind = typeof job.metadata?.error_kind === 'string' ? job.metadata.error_kind : '';
  const raw = `${rawKind} ${job.error || ''}`.toLowerCase();
  if (raw.includes('policy') || raw.includes('refus') || raw.includes('violat') || raw.includes('safety')) {
    return { title: 'Cannot generate this image', guidance: 'The provider refused this request because it may violate policy. Try changing the prompt.' };
  }
  if (raw.includes('rate') || raw.includes('too many') || raw.includes('429') || raw.includes('slow down')) {
    return { title: 'Generation is temporarily rate limited', guidance: 'Please wait a bit before trying again.' };
  }
  if (raw.includes('auth') || raw.includes('credential') || raw.includes('login')) {
    return { title: 'Provider connection needs attention', guidance: 'Reconnect or check the provider settings before retrying.' };
  }
  return { title: 'Generation failed', guidance: 'You can retry the job or adjust the prompt.' };
}

function buildInitialMetadata(job: GenerationJobRecord, item?: ItemDetail): GenerationJobAcceptAsNewItemPayload {
  const prompt = (job.edited_prompt_text || job.prompt_text || '').trim();
  return {
    title: item ? `${item.title} Variant` : 'Generated image',
    cluster_name: item?.cluster?.name || '',
    tags: item?.tags.map(tag => tag.name) || [],
    model: job.model || item?.model || 'ChatGPT Image2',
    source_name: 'Generation variant',
    source_url: item?.source_url || '',
    author: item?.author || '',
    notes: item ? `Variant generated from ${item.title}.` : 'Generated from a standalone prompt.',
    prompts: [{ language: job.prompt_language || 'en', text: prompt, is_primary: true, is_original: true }],
  };
}

export default function GenerationPanel({
  item,
  preferredLanguage,
  onClose,
  onAccepted,
  t,
}: {
  item?: ItemDetail;
  preferredLanguage: PromptCopyLanguage;
  onClose: () => void;
  onAccepted: (item?: ItemDetail, message?: string) => void;
  t: Translator;
}) {
  const originalPrompt = resolveOriginalPrompt(item?.prompts);
  const defaultPromptLanguage = preferredLanguage === 'origin' ? (originalPrompt?.language || 'en') : preferredLanguage;
  const defaultPrompt = item ? resolvePromptText(item.prompts, preferredLanguage, item.title) : '';
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [provider, setProvider] = useState('manual_upload');
  const [promptText, setPromptText] = useState(defaultPrompt);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [activeJobId, setActiveJobId] = useState<string>();
  const [reviewJob, setReviewJob] = useState<GenerationJobRecord>();
  const [metadataDraft, setMetadataDraft] = useState<GenerationJobAcceptAsNewItemPayload>();
  const metadataPanelRef = useRef<HTMLElement | null>(null);

  const activeJob = useMemo(() => jobs.find(job => job.id === activeJobId), [jobs, activeJobId]);
  const selectedProvider = providers.find(candidate => candidate.provider === provider);
  const primaryProviders = providers.filter(candidate => candidate.provider !== 'manual_upload');
  const panelTitle = item ? 'Generate variant' : 'Generate image';

  const refreshJobs = async () => {
    const result = await api.generationJobs({ limit: 100 });
    const nextJobs = result.jobs.filter(job => item ? job.source_item_id === item.id : !job.source_item_id);
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
  }, [item?.id]);

  useEffect(() => {
    if (!reviewJob || !metadataDraft) return;
    window.requestAnimationFrame(() => {
      metadataPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      metadataPanelRef.current?.focus({ preventScroll: true });
    });
  }, [reviewJob?.id]);

  const createJob = async () => {
    const prompt = promptText.trim();
    if (!prompt) return;
    setBusy(true);
    setMessage('');
    try {
      const created = await api.createGenerationJob({
        source_item_id: item?.id,
        mode: 'text_to_image',
        provider,
        model: provider === 'openai_codex_oauth_native' ? 'gpt-image-2' : null,
        prompt_language: defaultPromptLanguage,
        prompt_text: defaultPrompt || prompt,
        edited_prompt_text: prompt === defaultPrompt.trim() ? null : prompt,
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

  const acceptAttach = async (job: GenerationJobRecord) => {
    if (!item) return;
    setBusy(true);
    setMessage('');
    try {
      const result = await api.acceptGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === result.job.id ? result.job : candidate));
      setMessage('Image added to item');
      onAccepted(result.item, 'Image added to item');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not accept result.');
    } finally {
      setBusy(false);
    }
  };

  const openSaveAsNewReview = (job: GenerationJobRecord) => {
    setReviewJob(job);
    setMetadataDraft(buildInitialMetadata(job, item));
  };

  const updateMetadataDraft = (patch: Partial<GenerationJobAcceptAsNewItemPayload>) => {
    setMetadataDraft(current => ({ ...(current || {}), ...patch }));
  };

  const updatePromptDraft = (text: string) => {
    const currentPrompt = metadataDraft?.prompts?.[0] || { language: reviewJob?.prompt_language || 'en', text: '', is_primary: true, is_original: true };
    updateMetadataDraft({ prompts: [{ ...currentPrompt, text }] });
  };

  const acceptAsNew = async () => {
    if (!reviewJob || !metadataDraft) return;
    const metadataPayload = {
      ...metadataDraft,
      tags: typeof metadataDraft.tags === 'string' ? String(metadataDraft.tags).split(',').map(tag => tag.trim()).filter(Boolean) : metadataDraft.tags,
    } as GenerationJobAcceptAsNewItemPayload;
    setBusy(true);
    setMessage('');
    try {
      const result = await api.acceptGenerationJobAsNewItem(reviewJob.id, metadataPayload);
      setJobs(current => current.map(candidate => candidate.id === result.job.id ? result.job : candidate));
      setReviewJob(undefined);
      setMetadataDraft(undefined);
      setMessage('New variant item created');
      window.setTimeout(() => setMessage(''), 2200);
      onAccepted(result.item, 'New variant item created');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save new item.');
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
            <h2>{panelTitle}</h2>
            <p className="muted">Create a GenerationJob, then review the result before it enters the library.</p>
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
            <textarea value={promptText} onChange={event => setPromptText(event.currentTarget.value)} placeholder="Describe the image to generate" />
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
            {jobs.map(job => {
              const failure = job.status === 'failed' ? friendlyFailure(job) : undefined;
              return (
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
                  {failure && <div className="generation-failure"><strong>{failure.title}</strong><p>{failure.guidance}</p>{job.error && <small>{job.error}</small>}</div>}
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
                        {item && <button className="primary" onClick={() => acceptAttach(job)} disabled={busy}>Attach to current item</button>}
                        <button className="secondary" onClick={() => openSaveAsNewReview(job)} disabled={busy}>Save as new item</button>
                      </span>
                    )}
                    {!['accepted', 'discarded'].includes(job.status) && <button className="secondary" onClick={() => discardJob(job)} disabled={busy}>Discard</button>}
                  </div>
                </article>
              );
            })}
          </section>
        </div>
        {reviewJob && metadataDraft && (
          <section ref={metadataPanelRef} tabIndex={-1} className="save-new-metadata-panel" aria-label="Save generated image as new item">
            <div className="drawer-head">
              <div>
                <p className="drawer-eyebrow">Review metadata</p>
                <h3>Save generated image as new item</h3>
              </div>
              <button className="modal-icon-button" onClick={() => { setReviewJob(undefined); setMetadataDraft(undefined); }} aria-label={t('close')}>×</button>
            </div>
            <div className="save-new-metadata-grid">
              {jobResultUrl(reviewJob) && <img src={jobResultUrl(reviewJob)} alt="Generated result preview" />}
              <div className="save-new-fields">
                <label><span>Title</span><input value={metadataDraft.title || ''} onChange={event => updateMetadataDraft({ title: event.currentTarget.value })} /></label>
                <label><span>Collection</span><input value={metadataDraft.cluster_name || ''} onChange={event => updateMetadataDraft({ cluster_name: event.currentTarget.value })} /></label>
                <label><span>Model</span><input value={metadataDraft.model || ''} onChange={event => updateMetadataDraft({ model: event.currentTarget.value })} /></label>
                <label><span>Tags</span><input value={(metadataDraft.tags || []).join(', ')} onChange={event => updateMetadataDraft({ tags: event.currentTarget.value.split(',').map(tag => tag.trim()).filter(Boolean) })} /></label>
                <label><span>Prompt</span><textarea value={metadataDraft.prompts?.[0]?.text || ''} onChange={event => updatePromptDraft(event.currentTarget.value)} /></label>
                <label><span>Notes</span><textarea value={metadataDraft.notes || ''} onChange={event => updateMetadataDraft({ notes: event.currentTarget.value })} /></label>
                <div className="readonly-provenance">
                  <strong>Readonly provenance</strong>
                  <code>{reviewJob.id}</code>
                  {reviewJob.source_item_id && <code>{reviewJob.source_item_id}</code>}
                  <span>{reviewJob.provider} · {reviewJob.model || 'default model'}</span>
                </div>
                <span className="generation-actions">
                  <button className="primary" onClick={acceptAsNew} disabled={busy}>Confirm save</button>
                  <button className="secondary" onClick={() => { setReviewJob(undefined); setMetadataDraft(undefined); }} disabled={busy}>Cancel</button>
                </span>
              </div>
            </div>
          </section>
        )}
        {activeJob && <p className="muted">Selected job: <code>{activeJob.id}</code></p>}
        {message && <p className="provider-message">{message}</p>}
      </section>
    </div>
  );
}
