import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Clipboard, Clock3 } from 'lucide-react';
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
  if (status === 'accepted') return 'Saved';
  if (status === 'discarded') return 'Discarded';
  if (status === 'cancelled') return 'Cancelled';
  if (status === 'failed') return 'Failed';
  return status;
}

function jobResultUrl(job: GenerationJobRecord) {
  return job.result_path ? mediaUrl(job.result_path) : '';
}

const ASPECT_RATIO_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: '1:1', label: '1:1' },
  { value: '3:4', label: '3:4' },
  { value: '9:16', label: '9:16' },
  { value: '4:3', label: '4:3' },
  { value: '16:9', label: '16:9' },
];

const QUALITY_OPTIONS = [
  { value: 'standard', label: 'Standard' },
  { value: 'high', label: 'High' },
];

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

function jobPrompt(job?: GenerationJobRecord) {
  return job ? (job.edited_prompt_text || job.prompt_text || '').trim() : '';
}

function jobAspectRatio(job?: GenerationJobRecord) {
  const value = job?.parameters?.requested_aspect_ratio;
  return typeof value === 'string' && value ? value : '1:1';
}

function jobQuality(job?: GenerationJobRecord) {
  const value = job?.parameters?.quality;
  return typeof value === 'string' && ['standard', 'high'].includes(value) ? value : 'high';
}

function optionLabel(options: { value: string; label: string }[], value: string) {
  return options.find(option => option.value === value)?.label || value;
}

export default function GenerationPanel({
  item,
  preferredLanguage,
  onClose,
  onAccepted,
  t,
  initialJobId,
}: {
  item?: ItemDetail;
  preferredLanguage: PromptCopyLanguage;
  onClose: () => void;
  onAccepted: (item?: ItemDetail, message?: string) => void;
  t: Translator;
  initialJobId?: string;
}) {
  const originalPrompt = resolveOriginalPrompt(item?.prompts);
  const defaultPromptLanguage = preferredLanguage === 'origin' ? (originalPrompt?.language || 'en') : preferredLanguage;
  const defaultPrompt = item ? resolvePromptText(item.prompts, preferredLanguage, item.title) : '';
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [provider, setProvider] = useState('manual_upload');
  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [quality, setQuality] = useState('high');
  const [openControl, setOpenControl] = useState<'aspect' | 'quality' | null>(null);
  const [promptText, setPromptText] = useState(defaultPrompt);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [activeJobId, setActiveJobId] = useState<string | undefined>(initialJobId);
  const [focusedJobHighlightId, setFocusedJobHighlightId] = useState<string | undefined>(initialJobId);
  const [reviewJob, setReviewJob] = useState<GenerationJobRecord>();
  const [metadataDraft, setMetadataDraft] = useState<GenerationJobAcceptAsNewItemPayload>();
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [historyReviewJobId, setHistoryReviewJobId] = useState<string | undefined>(initialJobId);
  const metadataPanelRef = useRef<HTMLElement | null>(null);
  const focusedJobRef = useRef<HTMLDivElement | null>(null);

  const activeJob = useMemo(() => jobs.find(job => job.id === activeJobId), [jobs, activeJobId]);
  const historyReviewJob = useMemo(() => jobs.find(job => job.id === historyReviewJobId), [jobs, historyReviewJobId]);
  const selectedStageJob = historyReviewJob || activeJob;
  const visibleJobs = useMemo(() => jobs.filter(job => job.status !== 'discarded'), [jobs]);
  const isHistoryReview = Boolean(historyReviewJob);

  const refreshJobs = async (options: { preserveActive?: boolean } = {}) => {
    const result = await api.generationJobs({ limit: 100 });
    const nextJobs = result.jobs.filter(job => item ? job.source_item_id === item.id : !job.source_item_id);
    setJobs(nextJobs);
    const focusedJob = initialJobId ? nextJobs.find(job => job.id === initialJobId) : undefined;
    if (focusedJob) {
      setActiveJobId(focusedJob.id);
      setFocusedJobHighlightId(focusedJob.id);
      if (!historyReviewJobId) setHistoryReviewJobId(focusedJob.id);
    } else if (!options.preserveActive && !activeJobId && nextJobs[0]) {
      setActiveJobId(nextJobs[0].id);
    }
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
  }, [item?.id, initialJobId]);

  useEffect(() => {
    if (!initialJobId) return;
    setActiveJobId(initialJobId);
    setFocusedJobHighlightId(initialJobId);
    setHistoryReviewJobId(initialJobId);
  }, [initialJobId]);

  useEffect(() => {
    if (!jobs.some(job => ['queued', 'running'].includes(job.status))) return undefined;
    const timer = window.setInterval(() => refreshJobs({ preserveActive: true }).catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [jobs, item?.id, initialJobId]);

  useEffect(() => {
    if (!focusedJobHighlightId) return undefined;
    window.requestAnimationFrame(() => focusedJobRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    const timer = window.setTimeout(() => setFocusedJobHighlightId(undefined), 4200);
    return () => window.clearTimeout(timer);
  }, [focusedJobHighlightId]);

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
    setHistoryReviewJobId(undefined);
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
        parameters: {
          requested_aspect_ratio: aspectRatio,
          aspect_ratio_prompt_injection: true,
          quality,
        },
      });
      setJobs(current => [created, ...current.filter(job => job.id !== created.id)]);
      setActiveJobId(created.id);
      setMessage(provider === 'manual_upload' ? 'Job created. Upload a generated result when ready.' : 'Generation queued. It will start automatically.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create generation job.');
    } finally {
      setBusy(false);
    }
  };

  const runJob = async (job: GenerationJobRecord) => {
    setBusy(true);
    setActiveJobId(job.id);
    setHistoryReviewJobId(undefined);
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
      onClose();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save new item.');
    } finally {
      setBusy(false);
    }
  };

  const cancelJob = async (job: GenerationJobRecord) => {
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const updated = await api.cancelGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setMessage('Generation job cancelled.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not cancel job.');
      await refreshJobs().catch(() => undefined);
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
      if (activeJobId === updated.id) setActiveJobId(undefined);
      if (historyReviewJobId === updated.id) setHistoryReviewJobId(undefined);
      setMessage('Generation job discarded.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not discard job.');
    } finally {
      setBusy(false);
    }
  };

  const discardAndRetryJob = async (job: GenerationJobRecord) => {
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const result = await api.discardAndRetryGenerationJob(job.id);
      setJobs(current => [
        result.retry_job,
        ...current
          .map(candidate => candidate.id === result.discarded_job.id ? result.discarded_job : candidate)
          .filter(candidate => candidate.id !== result.retry_job.id),
      ]);
      setActiveJobId(result.retry_job.id);
      setHistoryReviewJobId(undefined);
      setPromptText(jobPrompt(result.retry_job));
      setAspectRatio(jobAspectRatio(result.retry_job));
      setQuality(jobQuality(result.retry_job));
      setProvider(result.retry_job.provider || provider);
      setFocusedJobHighlightId(result.retry_job.id);
      setMessage('Retry queued.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not retry job.');
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const previewHistoryJob = (job: GenerationJobRecord) => {
    setHistoryReviewJobId(job.id);
    setActiveJobId(job.id);
    setShowHistoryDrawer(false);
  };

  const useJobAsDraft = (job: GenerationJobRecord) => {
    setPromptText(jobPrompt(job));
    setAspectRatio(jobAspectRatio(job));
    setQuality(jobQuality(job));
    setProvider(job.provider || provider);
    setHistoryReviewJobId(undefined);
    setMessage('Prompt copied to draft.');
  };

  const copyJobPrompt = async (job: GenerationJobRecord) => {
    const text = jobPrompt(job);
    try {
      await navigator.clipboard?.writeText(text);
      setMessage('Prompt copied.');
    } catch {
      setMessage(text ? 'Prompt ready to copy.' : 'No prompt to copy.');
    }
  };

  const renderStageActions = (job: GenerationJobRecord) => (
    <div className="generation-stage-action-bar" aria-label="Result actions">
      <button className="stage-action" onClick={() => acceptAttach(job)} disabled={busy || !item || job.status !== 'succeeded'} title={item ? 'Attach to current item' : 'Open from an item to attach'}>
        Attach
      </button>
      <button className="stage-action primary" onClick={() => openSaveAsNewReview(job)} disabled={busy || job.status !== 'succeeded'} title="Save as new item">
        Save as new
      </button>
      <button className="stage-action" onClick={() => discardAndRetryJob(job)} disabled={busy || job.status !== 'succeeded'} aria-label="Retry" title="Retry">
        Retry
      </button>
      <button className="stage-action danger" onClick={() => discardJob(job)} disabled={busy || !['succeeded', 'failed'].includes(job.status)} title="Discard">
        Discard
      </button>
    </div>
  );

  const renderStage = () => {
    if (!selectedStageJob) {
      return <div className="generation-stage generation-stage-ready"><strong>Ready</strong></div>;
    }
    const resultUrl = jobResultUrl(selectedStageJob);
    if (selectedStageJob.status === 'queued' || selectedStageJob.status === 'running') {
      return (
        <div className="generation-stage generation-stage-generating">
          <div className="generation-generating-block generation-shimmer stage-shimmer" />
          <strong>Generating…</strong>
        </div>
      );
    }
    if (selectedStageJob.status === 'failed') {
      return (
        <div className="generation-stage generation-stage-error">
          <strong>Failed</strong>
        </div>
      );
    }
    if (resultUrl) {
      return (
        <div className="generation-stage generation-stage-result">
          <img className="generation-result-image generation-result-fade-in" src={resultUrl} alt="Generation result" />
          {renderStageActions(selectedStageJob)}
        </div>
      );
    }
    return (
      <div className="generation-stage generation-stage-ready">
        <strong>{statusLabel(selectedStageJob.status)}</strong>
        {renderStageActions(selectedStageJob)}
      </div>
    );
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="generation-panel modal polished-modal" onClick={event => event.stopPropagation()} aria-label="Generation workflow">
        <button className="modal-icon-button close generation-close" onClick={onClose} aria-label={t('close')}>×</button>

        <div className="generation-layout">
          <section className="generation-compose-card generation-composer-card">
            {!isHistoryReview ? (
              <>
                <label className="generation-prompt-area">
                  <span className="sr-only">Prompt</span>
                  <textarea value={promptText} onChange={event => setPromptText(event.currentTarget.value)} placeholder="Prompt" />
                </label>
                <div className="generation-compact-controls">
                  <div className="generation-control-wrap">
                    <button className="generation-control-trigger" type="button" onClick={() => setOpenControl(openControl === 'aspect' ? null : 'aspect')}>
                      {optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio)} ▾
                    </button>
                    {openControl === 'aspect' && (
                      <div className="generation-control-popover" role="menu">
                        {ASPECT_RATIO_OPTIONS.map(option => (
                          <button key={option.value} type="button" className={aspectRatio === option.value ? 'is-selected' : ''} onClick={() => { setAspectRatio(option.value); setOpenControl(null); }}>{option.label}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="generation-control-wrap">
                    <button className="generation-control-trigger" type="button" onClick={() => setOpenControl(openControl === 'quality' ? null : 'quality')}>
                      {optionLabel(QUALITY_OPTIONS, quality)} ▾
                    </button>
                    {openControl === 'quality' && (
                      <div className="generation-control-popover" role="menu">
                        {QUALITY_OPTIONS.map(option => (
                          <button key={option.value} type="button" className={quality === option.value ? 'is-selected' : ''} onClick={() => { setQuality(option.value); setOpenControl(null); }}>{option.label}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <button className="primary generation-primary-action" onClick={createJob} disabled={busy || !promptText.trim()}>Generate</button>
                </div>
              </>
            ) : historyReviewJob && (
              <div className="generation-history-prompt-preview">
                <textarea readOnly value={jobPrompt(historyReviewJob)} aria-label="Selected history prompt" />
                <div className="generation-history-prompt-actions">
                  <button className="primary" onClick={() => useJobAsDraft(historyReviewJob)}>Use as draft</button>
                  <button className="secondary" onClick={() => copyJobPrompt(historyReviewJob)}><Clipboard size={15} /> Copy prompt</button>
                  <button className="secondary" onClick={() => setHistoryReviewJobId(undefined)}><ArrowLeft size={15} /> Back to draft</button>
                </div>
              </div>
            )}
          </section>

          <section className="generation-stage-card">
            <button className="generation-history-overlay" onClick={() => setShowHistoryDrawer(true)} aria-label="History" title="History"><Clock3 size={17} /></button>
            {renderStage()}
          </section>
        </div>

        {showHistoryDrawer && (
          <aside className="generation-history-drawer" aria-label="Generation history">
            <div className="drawer-head">
              <div>
                <p className="drawer-eyebrow">History</p>
                <h3>Recent generations</h3>
              </div>
              <button className="modal-icon-button" onClick={() => setShowHistoryDrawer(false)} aria-label={t('close')}>×</button>
            </div>
            {visibleJobs.length === 0 && <p className="muted">No generation jobs yet.</p>}
            {visibleJobs.map(job => (
              <button key={job.id} className={`generation-history-item status-${job.status}`} onClick={() => previewHistoryJob(job)}>
                {jobResultUrl(job) ? <img src={jobResultUrl(job)} alt="" /> : <span className="generation-history-placeholder">{statusLabel(job.status)}</span>}
                <span>
                  <b>{jobPrompt(job) || 'Untitled generation'}</b>
                  <small>{jobAspectRatio(job)} · {jobQuality(job)} · {statusLabel(job.status)}</small>
                </span>
              </button>
            ))}
          </aside>
        )}

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
        {message && !selectedStageJob && <p className="provider-message generation-toast">{message}</p>}
      </section>
    </div>
  );
}
