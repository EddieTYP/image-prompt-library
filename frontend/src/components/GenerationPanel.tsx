import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Clipboard, Clock3, Download, FilePlus2, Maximize2, Paperclip, Plus, RotateCcw, Trash2, X } from 'lucide-react';
import aspectRatioIcon from '../assets/generation-controls/aspect-ratio.png';
import brainAiIcon from '../assets/generation-controls/model.png';
import qualityIcon from '../assets/generation-controls/quality.png';
import { api, mediaUrl } from '../api/client';
import type { ClusterRecord, GenerationJobAcceptAsNewItemPayload, GenerationJobRecord, GenerationProviderStatus, ItemDetail, TagRecord } from '../types';
import type { Translator } from '../utils/i18n';
import { downloadFileName } from '../utils/images';
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

function promptProvenance(language: string) {
  return { kind: 'manual', source_language: language, derived_from: null, method: null };
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
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];

const MAX_EDIT_ATTACHMENTS = 4;
const SAVE_NEW_LANGUAGE_OPTIONS = [
  { value: 'en', label: 'ENG' },
  { value: 'zh_hant', label: '繁中' },
  { value: 'zh_hans', label: '簡中' },
];

type EditAttachment = {
  id: string;
  name: string;
  source: 'uploaded' | 'generated_result';
  previewUrl: string;
  dataUrl?: string;
  resultPath?: string;
};

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
    author: 'User',
    notes: '',
    prompts: [{ language: job.prompt_language || 'en', text: prompt, is_primary: true, is_original: true, provenance: promptProvenance(job.prompt_language || 'en') }],
  };
}

function jobPrompt(job?: GenerationJobRecord) {
  return job ? (job.edited_prompt_text || job.prompt_text || '').trim() : '';
}

function jobAspectRatio(job?: GenerationJobRecord) {
  const value = job?.parameters?.requested_aspect_ratio;
  return typeof value === 'string' && value ? value : 'auto';
}

function jobQuality(job?: GenerationJobRecord) {
  const value = job?.parameters?.quality;
  if (value === 'standard') return 'medium';
  return typeof value === 'string' && ['low', 'medium', 'high'].includes(value) ? value : 'high';
}

function jobModel(job?: GenerationJobRecord) {
  const parameterModel = job?.parameters?.orchestrator_model;
  const metadataModel = job?.metadata?.orchestrator_model;
  if (typeof parameterModel === 'string' && parameterModel) return parameterModel;
  if (typeof metadataModel === 'string' && metadataModel) return metadataModel;
  return job?.model || 'Default';
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
  clusters = [],
  tags = [],
}: {
  item?: ItemDetail;
  preferredLanguage: PromptCopyLanguage;
  onClose: () => void;
  onAccepted: (item?: ItemDetail, message?: string) => void;
  t: Translator;
  initialJobId?: string;
  clusters?: ClusterRecord[];
  tags?: TagRecord[];
}) {
  const originalPrompt = resolveOriginalPrompt(item?.prompts);
  const defaultPromptLanguage = preferredLanguage === 'origin' ? (originalPrompt?.language || 'en') : preferredLanguage;
  const defaultPrompt = item ? resolvePromptText(item.prompts, preferredLanguage, item.title) : '';
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [provider, setProvider] = useState('manual_upload');
  const [orchestratorModel, setOrchestratorModel] = useState('gpt-5.4');
  const [aspectRatio, setAspectRatio] = useState('auto');
  const [quality, setQuality] = useState('high');
  const [openControl, setOpenControl] = useState<'aspect' | 'quality' | 'model' | null>(null);
  const [promptText, setPromptText] = useState(defaultPrompt);
  const [editAttachments, setEditAttachments] = useState<EditAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [activeJobId, setActiveJobId] = useState<string | undefined>(initialJobId);
  const [focusedJobHighlightId, setFocusedJobHighlightId] = useState<string | undefined>(initialJobId);
  const [reviewJob, setReviewJob] = useState<GenerationJobRecord>();
  const [metadataDraft, setMetadataDraft] = useState<GenerationJobAcceptAsNewItemPayload>();
  const [metadataTagsText, setMetadataTagsText] = useState('');
  const [metadataTagQuery, setMetadataTagQuery] = useState('');
  const [isSavePanelClosing, setIsSavePanelClosing] = useState(false);
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [historyReviewJobId, setHistoryReviewJobId] = useState<string | undefined>(initialJobId);
  const [isClosing, setIsClosing] = useState(false);
  const [isStageFullscreen, setIsStageFullscreen] = useState(false);
  const metadataPanelRef = useRef<HTMLElement | null>(null);
  const focusedJobRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLElement | null>(null);
  const resultImageRef = useRef<HTMLImageElement | null>(null);
  const fullscreenFrameRef = useRef<HTMLDivElement | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const initialFocusAppliedRef = useRef(false);

  const activeJob = useMemo(() => jobs.find(job => job.id === activeJobId), [jobs, activeJobId]);
  const historyReviewJob = useMemo(() => jobs.find(job => job.id === historyReviewJobId), [jobs, historyReviewJobId]);
  const selectedStageJob = historyReviewJob || activeJob;
  const visibleJobs = useMemo(() => jobs.filter(job => job.status !== 'discarded'), [jobs]);
  const selectedProvider = useMemo(() => providers.find(candidate => candidate.provider === provider), [providers, provider]);
  const orchestratorModels = selectedProvider?.orchestrator_models || ['gpt-5.4'];
  const promptChangedFromSource = promptText.trim() !== defaultPrompt.trim();
  const canAttachToSourceItem = (job?: GenerationJobRecord) => Boolean(item && job?.source_item_id === item.id && !promptChangedFromSource);
  const isHistoryReview = Boolean(historyReviewJob);
  const canUseResultActions = (job?: GenerationJobRecord) => Boolean(job && job.status === 'succeeded' && !job.accepted_image_id);
  const filteredMetadataTags = useMemo(() => {
    const selected = new Set(metadataTagsText.split(',').map(tag => tag.trim()).filter(Boolean));
    const query = metadataTagQuery.trim().toLowerCase();
    return tags
      .filter(tag => !selected.has(tag.name) && (!query || tag.name.toLowerCase().includes(query)))
      .slice(0, 10);
  }, [metadataTagsText, metadataTagQuery, tags]);
  const filteredMetadataClusters = useMemo(() => {
    const query = (metadataDraft?.cluster_name || '').trim().toLowerCase();
    if (!query) return clusters.slice(0, 8);
    return clusters.filter(cluster => cluster.name.toLowerCase().includes(query)).slice(0, 8);
  }, [metadataDraft?.cluster_name, clusters]);

  const refreshJobs = async (options: { preserveActive?: boolean } = {}) => {
    const result = await api.generationJobs({ limit: 100 });
    const nextJobs = result.jobs.filter(job => item ? job.source_item_id === item.id : !job.source_item_id);
    setJobs(nextJobs);
    const focusedJob = initialJobId && !initialFocusAppliedRef.current ? nextJobs.find(job => job.id === initialJobId) : undefined;
    if (focusedJob) {
      initialFocusAppliedRef.current = true;
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
        if (firstReady) {
          setProvider(firstReady.provider);
          setOrchestratorModel(firstReady.default_orchestrator_model || firstReady.orchestrator_models?.[0] || 'gpt-5.4');
        }
      })
      .catch(() => setProviders([{ provider: 'manual_upload', display_name: 'Manual upload', optional: false, configured: true, authenticated: true, available: true, state: 'available', reason: null, features: { manual_result_upload: true } }]));
    refreshJobs().catch(() => undefined);
    return () => { cancelled = true; };
  }, [item?.id, initialJobId]);

  useEffect(() => {
    if (!initialJobId) return;
    initialFocusAppliedRef.current = false;
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

  useEffect(() => {
    const syncFullscreenState = () => setIsStageFullscreen(document.fullscreenElement === fullscreenFrameRef.current);
    document.addEventListener('fullscreenchange', syncFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState);
  }, []);

  useEffect(() => {
    if (selectedStageJob?.status !== 'succeeded') return;
    window.requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }, [selectedStageJob?.id, selectedStageJob?.status]);

  const closeStageFullscreen = async () => {
    if (document.fullscreenElement === fullscreenFrameRef.current) {
      await document.exitFullscreen?.();
    }
    setIsStageFullscreen(false);
  };

  const createJob = async () => {
    const prompt = promptText.trim();
    if (!prompt) return;
    setBusy(true);
    setMessage('');
    setHistoryReviewJobId(undefined);
    window.requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    try {
      const attachments = imageAttachmentPayload();
      const created = await api.createGenerationJob({
        source_item_id: item?.id,
        mode: attachments.length > 0 ? 'image_edit' : 'text_to_image',
        provider,
        model: provider === 'openai_codex_oauth_native' ? 'gpt-image-2' : null,
        prompt_language: defaultPromptLanguage,
        prompt_text: defaultPrompt || prompt,
        edited_prompt_text: prompt === defaultPrompt.trim() ? null : prompt,
        reference_image_ids: [],
        parameters: {
          requested_aspect_ratio: aspectRatio,
          aspect_ratio_prompt_injection: aspectRatio !== 'auto',
          quality,
          orchestrator_model: orchestratorModel,
          input_images: attachments,
        },
      });
      setJobs(current => [created, ...current.filter(job => job.id !== created.id)]);
      setActiveJobId(created.id);
      window.requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
      setMessage(provider === 'manual_upload' ? 'Job created. Upload a generated result when ready.' : attachments.length > 0 ? 'Edit queued. It will start automatically.' : 'Generation queued. It will start automatically.');
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
      onClose();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not accept result.');
    } finally {
      setBusy(false);
    }
  };

  const openSaveAsNewReview = (job: GenerationJobRecord) => {
    const initialMetadata = buildInitialMetadata(job, item);
    setIsSavePanelClosing(false);
    setReviewJob(job);
    setMetadataDraft(initialMetadata);
    setMetadataTagsText((initialMetadata.tags || []).join(', '));
    setMetadataTagQuery('');
  };

  const closeSaveAsNewReview = () => {
    setIsSavePanelClosing(true);
    window.setTimeout(() => {
      setReviewJob(undefined);
      setMetadataDraft(undefined);
      setMetadataTagsText('');
      setMetadataTagQuery('');
      setIsSavePanelClosing(false);
    }, 180);
  };

  const handleClose = () => {
    setIsClosing(true);
    window.setTimeout(onClose, 180);
  };

  const toggleStageFullscreen = async () => {
    if (document.fullscreenElement === fullscreenFrameRef.current || isStageFullscreen) {
      await closeStageFullscreen();
      return;
    }
    if (!fullscreenFrameRef.current) return;
    try {
      if (fullscreenFrameRef.current.requestFullscreen) {
        await fullscreenFrameRef.current.requestFullscreen();
      } else {
        setIsStageFullscreen(true);
      }
    } catch {
      setIsStageFullscreen(true);
    }
  };

  const imageAttachmentPayload = () => editAttachments.map(attachment => ({
    id: attachment.id,
    name: attachment.name,
    source: attachment.source,
    data_url: attachment.dataUrl,
    result_path: attachment.resultPath,
  }));

  const addUploadedAttachments = async (files: FileList | null) => {
    const nextFiles = Array.from(files || []).filter(file => file.type.startsWith('image/'));
    if (nextFiles.length === 0) return;
    const slots = MAX_EDIT_ATTACHMENTS - editAttachments.length;
    const limitedFiles = nextFiles.slice(0, Math.max(0, slots));
    const loaded = await Promise.all(limitedFiles.map(file => new Promise<EditAttachment>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({ id: `upload-${Date.now()}-${file.name}-${Math.random().toString(36).slice(2)}`, name: file.name, source: 'uploaded', previewUrl: String(reader.result), dataUrl: String(reader.result) });
      reader.onerror = () => reject(reader.error || new Error('Could not read image attachment.'));
      reader.readAsDataURL(file);
    })));
    setEditAttachments(current => [...current, ...loaded].slice(0, MAX_EDIT_ATTACHMENTS));
    setMessage(loaded.length < nextFiles.length ? `Attached ${loaded.length} image(s). Limit is ${MAX_EDIT_ATTACHMENTS}.` : 'Image attached for editing.');
    if (attachmentInputRef.current) attachmentInputRef.current.value = '';
  };

  const removeAttachment = (id: string) => {
    setEditAttachments(current => current.filter(attachment => attachment.id !== id));
  };

  const addResultAsAttachment = (job: GenerationJobRecord) => {
    if (!job.result_path || editAttachments.length >= MAX_EDIT_ATTACHMENTS) return;
    setEditAttachments(current => {
      if (current.some(attachment => attachment.resultPath === job.result_path)) return current;
      const resultAttachment: EditAttachment = {
        id: `result-${job.id}`,
        name: `${job.id}.png`,
        source: 'generated_result',
        previewUrl: jobResultUrl(job),
        resultPath: job.result_path || undefined,
      };
      return [...current, resultAttachment].slice(0, MAX_EDIT_ATTACHMENTS);
    });
    setHistoryReviewJobId(undefined);
    setMessage('Result attached as edit input.');
  };

  const updateMetadataDraft = (patch: Partial<GenerationJobAcceptAsNewItemPayload>) => {
    setMetadataDraft(current => ({ ...(current || {}), ...patch }));
  };

  const updatePromptDraft = (text: string) => {
    const currentPrompt = metadataDraft?.prompts?.[0] || { language: reviewJob?.prompt_language || 'en', text: '', is_primary: true, is_original: true };
    updateMetadataDraft({ prompts: [{ ...currentPrompt, text }] });
  };

  const updateMetadataPromptLanguage = (language: string) => {
    const currentPrompt = metadataDraft?.prompts?.[0] || { language, text: '', is_primary: true, is_original: true };
    updateMetadataDraft({ prompts: [{ ...currentPrompt, language, is_primary: true, is_original: true, provenance: { kind: 'manual', source_language: language, derived_from: null, method: null } }] });
  };

  const addSuggestedMetadataTag = (tagName: string) => {
    const currentTags = metadataTagsText.split(',').map(tag => tag.trim()).filter(Boolean);
    const selected = new Set(currentTags);
    selected.add(tagName);
    setMetadataTagsText(Array.from(selected).join(', '));
    setMetadataTagQuery('');
  };

  const acceptAsNew = async () => {
    if (!reviewJob || !metadataDraft) return;
    const metadataPayload = {
      ...metadataDraft,
      tags: metadataTagsText.split(',').map(tag => tag.trim()).filter(Boolean),
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
    <div className="generation-stage-actions" aria-label="Result actions">
      {canAttachToSourceItem(job) && (
        <button className="stage-action" onClick={() => acceptAttach(job)} disabled={busy} aria-label="Attach to current item" title="Attach to current item">
          <Paperclip size={16} aria-hidden="true" />
        </button>
      )}
      <button className="stage-action" onClick={() => openSaveAsNewReview(job)} disabled={busy} aria-label="Save as new item" title="Save as new item">
        <FilePlus2 size={16} aria-hidden="true" />
      </button>
      <button className="stage-action" onClick={() => addResultAsAttachment(job)} disabled={busy || editAttachments.length >= MAX_EDIT_ATTACHMENTS || !job.result_path} aria-label="Use result as edit input" title="Use result as edit input">
        <Plus size={16} aria-hidden="true" />
      </button>
      <button className="stage-action" onClick={() => discardAndRetryJob(job)} disabled={busy} aria-label="Retry" title="Retry">
        <RotateCcw size={16} aria-hidden="true" />
      </button>
      <button className="stage-action danger" onClick={() => discardJob(job)} disabled={busy} aria-label="Discard" title="Discard">
        <Trash2 size={16} aria-hidden="true" />
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
        <div className={`generation-stage generation-stage-result${isStageFullscreen ? ' is-mobile-fullscreen' : ''}`}>
          <div ref={fullscreenFrameRef} className="generation-fullscreen-frame">
            <img ref={resultImageRef} className="generation-result-image generation-result-fade-in" src={resultUrl} alt="Generation result" />
            <button className="modal-icon-button generation-fullscreen-close" type="button" onClick={closeStageFullscreen} aria-label="Close fullscreen"><X size={20} strokeWidth={2.25} /></button>
          </div>
          {canUseResultActions(selectedStageJob) && renderStageActions(selectedStageJob)}
        </div>
      );
    }
    if (selectedStageJob.status === 'accepted') {
      return <div className="generation-stage generation-stage-ready"><strong>Saved</strong></div>;
    }
    return (
      <div className="generation-stage generation-stage-ready">
        <strong>{statusLabel(selectedStageJob.status)}</strong>
        {renderStageActions(selectedStageJob)}
      </div>
    );
  };

  return (
    <div className={`modal-backdrop${isClosing ? ' is-closing' : ''}`} onClick={handleClose}>
      <section className="generation-panel modal polished-modal" onClick={event => event.stopPropagation()} aria-label="Generation workflow">
        <div className="generation-layout">
          <section className="generation-compose-card generation-composer-card">
            {!isHistoryReview ? (
              <>
                <label className="generation-prompt-area">
                  <span className="sr-only">Prompt</span>
                  <textarea value={promptText} onChange={event => setPromptText(event.currentTarget.value)} placeholder="Prompt" />
                  {editAttachments.length > 0 && (
                    <div className="generation-attachment-strip" aria-label="Edit input images">
                      {editAttachments.map(attachment => (
                        <span className="generation-attachment-thumb" key={attachment.id} title={attachment.name}>
                          <img src={attachment.previewUrl} alt="Edit input" />
                          <em>{attachment.source === 'generated_result' ? 'Ref' : 'Upload'}</em>
                          <button type="button" onClick={event => { event.preventDefault(); removeAttachment(attachment.id); }} aria-label={`Remove ${attachment.name}`} title="Remove image"><X size={11} /></button>
                        </span>
                      ))}
                    </div>
                  )}
                </label>
                <div className="generation-compact-controls">
                  <div className="generation-control-wrap">
                    <button className="generation-control-trigger generation-aspect-trigger" type="button" onClick={() => setOpenControl(openControl === 'aspect' ? null : 'aspect')} aria-label={`Aspect ratio: ${optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio)}`} title={`Aspect ratio: ${optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio)}`}>
                      <img className="generation-control-icon" src={aspectRatioIcon} alt="" aria-hidden="true" />
                      <span className="generation-control-value">{optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio)}</span>
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
                    <button className="generation-control-trigger generation-quality-trigger" type="button" onClick={() => setOpenControl(openControl === 'quality' ? null : 'quality')} aria-label={`Quality: ${optionLabel(QUALITY_OPTIONS, quality)}`} title={`Quality: ${optionLabel(QUALITY_OPTIONS, quality)}`}>
                      <img className="generation-control-icon" src={qualityIcon} alt="" aria-hidden="true" />
                      <span className="generation-control-value">{optionLabel(QUALITY_OPTIONS, quality)}</span>
                    </button>
                    {openControl === 'quality' && (
                      <div className="generation-control-popover" role="menu">
                        {QUALITY_OPTIONS.map(option => (
                          <button key={option.value} type="button" className={quality === option.value ? 'is-selected' : ''} onClick={() => { setQuality(option.value); setOpenControl(null); }}>{option.label}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="generation-control-wrap generation-model-control">
                    <button className="generation-control-trigger generation-model-trigger generation-has-long-value" type="button" onClick={() => setOpenControl(openControl === 'model' ? null : 'model')} disabled={provider !== 'openai_codex_oauth_native'} aria-label={`Model: ${orchestratorModel}`} title={orchestratorModel}>
                      <img className="generation-control-icon" src={brainAiIcon} alt="" aria-hidden="true" />
                      <span className="generation-control-value">{orchestratorModel}</span>
                    </button>
                    {openControl === 'model' && (
                      <div className="generation-control-popover" role="menu">
                        {orchestratorModels.map(model => (
                          <button key={model} type="button" className={orchestratorModel === model ? 'is-selected' : ''} onClick={() => { setOrchestratorModel(model); setOpenControl(null); }}>{model}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <input ref={attachmentInputRef} className="generation-attachment-input" type="file" accept="image/*" multiple onChange={event => addUploadedAttachments(event.currentTarget.files)} />
                  <button className="generation-control-trigger generation-attach-trigger" type="button" onClick={() => attachmentInputRef.current?.click()} disabled={editAttachments.length >= MAX_EDIT_ATTACHMENTS} aria-label="Attach image" title={editAttachments.length >= MAX_EDIT_ATTACHMENTS ? 'Maximum 4 images' : 'Attach image'}>
                    <Plus size={18} aria-hidden="true" />
                  </button>
                  <button className="primary generation-primary-action" onClick={createJob} disabled={busy || !promptText.trim()}>Generate</button>
                  <button className="generation-history-control" onClick={() => setShowHistoryDrawer(true)} aria-label="History" title="History" type="button"><Clock3 size={17} /></button>
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

          <section ref={stageRef} className="generation-stage-card">
            {selectedStageJob?.result_path && <a className="modal-icon-button generation-download-overlay" href={jobResultUrl(selectedStageJob)} download={downloadFileName('generation-result', selectedStageJob.result_path)} aria-label="Download" title="Download"><Download size={16} /></a>}
            <button className="modal-icon-button generation-fullscreen-overlay" onClick={toggleStageFullscreen} aria-label="View fullscreen" title="View fullscreen"><Maximize2 size={16} /></button>
            <button className="modal-icon-button close generation-close-overlay" onClick={handleClose} aria-label={t('close')}><X size={20} strokeWidth={2.25} /></button>
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
              <button className="modal-icon-button" onClick={() => setShowHistoryDrawer(false)} aria-label={t('close')}><X size={20} strokeWidth={2.25} /></button>
            </div>
            {visibleJobs.length === 0 && <p className="muted">No generation jobs yet.</p>}
            {visibleJobs.map(job => (
              <button key={job.id} className={`generation-history-item status-${job.status}`} onClick={() => previewHistoryJob(job)} aria-label={`${statusLabel(job.status)} generation, ${jobAspectRatio(job)}, ${jobQuality(job)}, ${jobModel(job)}`}>
                <span className="generation-history-media">
                  {jobResultUrl(job) ? <img src={jobResultUrl(job)} alt="" /> : <span className="generation-history-placeholder">{statusLabel(job.status)}</span>}
                </span>
                <span className="generation-history-status-grid" aria-hidden="true">
                  <span className="generation-history-cell"><b>Aspect ratio</b><em>{optionLabel(ASPECT_RATIO_OPTIONS, jobAspectRatio(job))}</em></span>
                  <span className="generation-history-cell"><b>Quality</b><em>{optionLabel(QUALITY_OPTIONS, jobQuality(job))}</em></span>
                  <span className="generation-history-cell"><b>Model</b><em>{jobModel(job)}</em></span>
                  <span className="generation-history-cell"><b>Status</b><em>{statusLabel(job.status)}</em></span>
                </span>
              </button>
            ))}
          </aside>
        )}

        {reviewJob && metadataDraft && (
          <section ref={metadataPanelRef} tabIndex={-1} className={`save-new-metadata-panel${isSavePanelClosing ? ' is-closing' : ''}`} aria-label="Save generated image as new item">
            <div className="drawer-head">
              <div>
                <p className="drawer-eyebrow">Review metadata</p>
                <h3>Save generated image as new item</h3>
              </div>
              <button className="modal-icon-button generation-save-panel-close" onClick={closeSaveAsNewReview} aria-label={t('close')}><X size={20} strokeWidth={2.25} /></button>
            </div>
            <div className="save-new-metadata-grid">
              {jobResultUrl(reviewJob) && <img src={jobResultUrl(reviewJob)} alt="Generated result preview" />}
              <div className="save-new-fields">
                <label><span>Title</span><input value={metadataDraft.title || ''} onChange={event => updateMetadataDraft({ title: event.currentTarget.value })} /></label>
                <label><span>Collection</span><input list="save-new-collection-suggestions" value={metadataDraft.cluster_name || ''} onChange={event => updateMetadataDraft({ cluster_name: event.currentTarget.value })} /></label>
                <datalist id="save-new-collection-suggestions">
                  {filteredMetadataClusters.map(collection => <option key={collection.id} value={collection.name} />)}
                </datalist>
                <label><span>Model</span><input value={metadataDraft.model || ''} onChange={event => updateMetadataDraft({ model: event.currentTarget.value })} /></label>
                <label><span>Tags</span><input list="save-new-tag-suggestions" placeholder={t('tagsPlaceholder')} value={metadataTagsText} onChange={event => { setMetadataTagsText(event.currentTarget.value); setMetadataTagQuery(event.currentTarget.value.split(',').pop()?.trim() || ''); }} /></label>
                <datalist id="save-new-tag-suggestions">
                  {filteredMetadataTags.map(tag => <option key={tag.id} value={tag.name} />)}
                </datalist>
                {filteredMetadataTags.length > 0 && <div className="tag-suggestions" aria-label={t('existingTagSuggestions')}>
                  {filteredMetadataTags.map(tag => <button type="button" key={tag.id} onClick={() => addSuggestedMetadataTag(tag.name)}>#{tag.name}</button>)}
                </div>}
                <label className="save-new-prompt-field"><span className="prompt-field-title">Prompt <span className="save-new-language-pills" aria-label="Original prompt language"><span>原文</span>{SAVE_NEW_LANGUAGE_OPTIONS.map(language => <button type="button" key={language.value} className={`origin-marker ${metadataDraft.prompts?.[0]?.language === language.value ? 'active' : ''}`} onClick={() => updateMetadataPromptLanguage(language.value)}>{language.label}</button>)}</span></span><textarea value={metadataDraft.prompts?.[0]?.text || ''} onChange={event => updatePromptDraft(event.currentTarget.value)} /></label>
                <label><span>Notes</span><textarea value={metadataDraft.notes || ''} onChange={event => updateMetadataDraft({ notes: event.currentTarget.value })} /></label>
                <div className="readonly-provenance">
                  <strong>Readonly provenance</strong>
                  <code>{reviewJob.id}</code>
                  {reviewJob.source_item_id && <code>{reviewJob.source_item_id}</code>}
                  <span>{reviewJob.provider} · {reviewJob.model || 'default model'}</span>
                </div>
                <span className="generation-actions">
                  <button className="primary" onClick={acceptAsNew} disabled={busy}>Confirm save</button>
                  <button className="secondary" onClick={closeSaveAsNewReview} disabled={busy}>Cancel</button>
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
