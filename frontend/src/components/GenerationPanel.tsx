import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, ChevronDown, ChevronLeft, ChevronRight, Clipboard, Clock3, Download, FilePlus2, Images, Maximize2, Paperclip, Plus, RotateCcw, Trash2, Upload, X } from 'lucide-react';
import aspectRatioIcon from '../assets/generation-controls/aspect-ratio.png';
import brainAiIcon from '../assets/generation-controls/model.png';
import qualityIcon from '../assets/generation-controls/quality.png';
import { api, mediaUrl } from '../api/client';
import type { ClusterRecord, GenerationJobAcceptAsNewItemPayload, GenerationJobCreate, GenerationJobRecord, GenerationJobSetRecord, GenerationProviderQueueState, GenerationProviderStatus, GenerationSetCount, ImageRecord, ItemDetail, ItemSummary, TagRecord } from '../types';
import type { Translator } from '../utils/i18n';
import { generationSetProgressText, providerPauseSeconds } from '../utils/generationSets';
import { downloadFileName } from '../utils/images';
import { generationFailure } from '../utils/generationFailures';
import { resolveOriginalPrompt, resolvePromptText, type PromptCopyLanguage } from '../utils/prompts';
import { extractPromptTemplateVariableRecords, resolvePromptTemplate } from '../utils/promptTemplateVariables';

function providerReady(provider: GenerationProviderStatus) {
  if (provider.provider === 'manual_upload') return true;
  return Boolean(provider.available && provider.authenticated && provider.configured);
}

function providerCanGenerate(provider?: GenerationProviderStatus) {
  if (!provider) return false;
  return provider.can_generate ?? providerReady(provider);
}

function providerReadinessLabel(provider?: GenerationProviderStatus) {
  if (!provider) return 'Provider unavailable';
  if (providerCanGenerate(provider)) return `${provider.display_name} ready`;
  if (provider.message) return provider.message;
  if (provider.status === 'login_required' || provider.state === 'not_connected') return `Connect ${provider.display_name} before generating.`;
  if (provider.status === 'auth_error') return `${provider.display_name} needs attention before generating.`;
  return `${provider.display_name} is unavailable.`;
}

function compactProviderReadinessLabel(provider?: GenerationProviderStatus) {
  if (providerCanGenerate(provider)) return 'Ready';
  return providerReadinessLabel(provider);
}

function statusLabel(status: string, isUsedAsGenerationReference = false) {
  if (status === 'queued') return 'Queued';
  if (status === 'running') return 'Running';
  if (status === 'succeeded') return isUsedAsGenerationReference ? 'Used as ref' : 'Ready';
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
  source: 'uploaded' | 'generated_result' | 'library';
  previewUrl: string;
  dataUrl?: string;
  resultPath?: string;
  imageId?: string;
  sourceItemId?: string;
  role?: string;
};

function libraryAttachment(image: ImageRecord, title: string): EditAttachment {
  return {
    id: `library-${image.id}`,
    name: title,
    source: 'library',
    previewUrl: mediaUrl(image.preview_path || image.thumb_path || image.original_path),
    imageId: image.id,
    sourceItemId: image.item_id,
    role: image.role,
  };
}

function jobAttachments(job?: GenerationJobRecord): EditAttachment[] {
  const inputs = job?.parameters?.input_images;
  if (!Array.isArray(inputs)) return [];
  return inputs.flatMap((raw, index) => {
    if (!raw || typeof raw !== 'object') return [];
    const input = raw as Record<string, unknown>;
    const source = input.source === 'library' ? 'library' : input.source === 'generated_result' ? 'generated_result' : 'uploaded';
    const resultPath = typeof input.result_path === 'string' ? input.result_path : undefined;
    const previewPath = typeof input.preview_path === 'string' ? input.preview_path : undefined;
    return [{
      id: typeof input.id === 'string' ? input.id : `job-${job?.id}-${index}`,
      name: typeof input.name === 'string' ? input.name : `Reference ${index + 1}`,
      source,
      previewUrl: previewPath ? mediaUrl(previewPath) : resultPath ? mediaUrl(resultPath) : '',
      resultPath,
      imageId: typeof input.image_id === 'string' ? input.image_id : undefined,
      sourceItemId: typeof input.source_item_id === 'string' ? input.source_item_id : undefined,
      role: typeof input.role === 'string' ? input.role : undefined,
    }];
  });
}

function restorableJobAttachments(job?: GenerationJobRecord): EditAttachment[] {
  return jobAttachments(job).filter(attachment => Boolean(attachment.dataUrl || attachment.resultPath || attachment.imageId));
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

const STALE_RUNNING_JOB_MS = 10 * 60 * 1000;

function retriedByJobId(job?: GenerationJobRecord) {
  const value = job?.metadata?.retried_by_generation_job_id;
  return typeof value === 'string' && value ? value : '';
}

function canRetryFailedJob(job?: GenerationJobRecord) {
  return job?.status === 'failed' && !retriedByJobId(job);
}

function isStaleRunningJob(job?: GenerationJobRecord) {
  if (job?.status !== 'running') return false;
  const started = Date.parse(job.started_at || job.updated_at || job.created_at);
  return Number.isFinite(started) && Date.now() - started > STALE_RUNNING_JOB_MS;
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

function mergeGenerationJobs(current: GenerationJobRecord[], incoming: GenerationJobRecord[]) {
  const incomingIds = new Set(incoming.map(job => job.id));
  return [...incoming, ...current.filter(job => !incomingIds.has(job.id))];
}

const GENERATION_SET_OPTIONS: Exclude<GenerationSetCount, 1>[] = [3, 5, 10];

export default function GenerationPanel({
  item,
  preferredLanguage,
  onClose,
  onOpenProviders,
  onAccepted,
  t,
  initialJobId,
  clusters = [],
  tags = [],
  promptVariablesEnabled = false,
}: {
  item?: ItemDetail;
  preferredLanguage: PromptCopyLanguage;
  onClose: () => void;
  onOpenProviders: () => void;
  onAccepted: (item?: ItemDetail, message?: string) => void;
  t: Translator;
  initialJobId?: string;
  clusters?: ClusterRecord[];
  tags?: TagRecord[];
  promptVariablesEnabled?: boolean;
}) {
  const originalPrompt = resolveOriginalPrompt(item?.prompts);
  const defaultPromptLanguage = preferredLanguage === 'origin' ? (originalPrompt?.language || 'en') : preferredLanguage;
  const defaultPrompt = item ? resolvePromptText(item.prompts, preferredLanguage, item.title) : '';
  const [providers, setProviders] = useState<GenerationProviderStatus[]>([]);
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [activeGenerationSet, setActiveGenerationSet] = useState<GenerationJobSetRecord>();
  const [providerQueueStates, setProviderQueueStates] = useState<GenerationProviderQueueState[]>([]);
  const [provider, setProvider] = useState('manual_upload');
  const [orchestratorModel, setOrchestratorModel] = useState('gpt-5.6-luna');
  const [aspectRatio, setAspectRatio] = useState('auto');
  const [quality, setQuality] = useState('high');
  const [openControl, setOpenControl] = useState<'aspect' | 'quality' | 'model' | null>(null);
  const [generationCountMenuOpen, setGenerationCountMenuOpen] = useState(false);
  const [cancelSetBusy, setCancelSetBusy] = useState(false);
  const [queueClock, setQueueClock] = useState(() => Date.now());
  const [promptText, setPromptText] = useState(defaultPrompt);
  const [editAttachments, setEditAttachments] = useState<EditAttachment[]>([]);
  const [referenceMenuOpen, setReferenceMenuOpen] = useState(false);
  const [referencePicker, setReferencePicker] = useState<'library' | 'recent' | null>(null);
  const [libraryItems, setLibraryItems] = useState<ItemSummary[]>([]);
  const [libraryQuery, setLibraryQuery] = useState('');
  const [libraryItem, setLibraryItem] = useState<ItemDetail>();
  const [recentJobs, setRecentJobs] = useState<GenerationJobRecord[]>([]);
  const [pickerBusy, setPickerBusy] = useState(false);
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
  const generationCountMenuRef = useRef<HTMLDivElement | null>(null);
  const generationCountTriggerRef = useRef<HTMLButtonElement | null>(null);
  const generationCountFocusOnOpenRef = useRef(false);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const promptInputRef = useRef<HTMLTextAreaElement | null>(null);
  const initialFocusAppliedRef = useRef(false);

  const activeJob = useMemo(() => jobs.find(job => job.id === activeJobId), [jobs, activeJobId]);
  const historyReviewJob = useMemo(() => jobs.find(job => job.id === historyReviewJobId), [jobs, historyReviewJobId]);
  const selectedStageJob = (historyReviewJob || activeJob)?.status !== 'discarded' ? (historyReviewJob || activeJob) : undefined;
  const visibleJobs = useMemo(() => jobs.filter(job => job.status !== 'discarded'), [jobs]);
  const selectedProvider = useMemo(() => providers.find(candidate => candidate.provider === provider), [providers, provider]);
  const selectedProviderCanGenerate = providerCanGenerate(selectedProvider);
  const selectedProviderMessage = providerReadinessLabel(selectedProvider);
  const compactProviderMessage = compactProviderReadinessLabel(selectedProvider);
  const selectedProviderQueueState = providerQueueStates.find(state => state.provider === provider);
  const selectedProviderPauseSeconds = selectedProviderQueueState ? providerPauseSeconds(selectedProviderQueueState, queueClock) : 0;
  const orchestratorModels = selectedProvider?.orchestrator_models || ['gpt-5.6-luna'];
  const templateVariables = useMemo(() => promptVariablesEnabled ? extractPromptTemplateVariableRecords(promptText) : [], [promptVariablesEnabled, promptText]);
  const [templateValues, setTemplateValues] = useState<Record<string, string>>({});
  const hasTemplateVariables = templateVariables.length > 0;
  const hasMissingTemplateValues = hasTemplateVariables && templateVariables.some(variable => !templateValues[variable.key]?.trim());
  const resolvedPrompt = hasTemplateVariables ? resolvePromptTemplate(promptText, templateValues).trim() : promptText.trim();
  const promptChangedFromSource = hasTemplateVariables ? resolvedPrompt !== defaultPrompt.trim() : promptText.trim() !== defaultPrompt.trim();
  const promptTemplateValues = useMemo(() => Object.fromEntries(templateVariables.map(variable => [variable.key, templateValues[variable.key] || ''])), [templateVariables, templateValues]);
  const templateVariableKeySignature = useMemo(() => templateVariables.map(variable => variable.key).join('\u0000'), [templateVariables]);
  const canAttachToSourceItem = (job?: GenerationJobRecord) => Boolean(item && job?.source_item_id === item.id && !promptChangedFromSource);
  const isHistoryReview = Boolean(historyReviewJob);
  const canUseResultActions = (job?: GenerationJobRecord) => Boolean(job && job.status === 'succeeded' && !job.accepted_image_id && job.result_path);
  const canDiscardTransientResult = (job?: GenerationJobRecord) => canUseResultActions(job) && Boolean(job?.result_path?.startsWith(`generation-results/${job.id}/`));
  const isUsedAsGenerationReference = (job?: GenerationJobRecord) => {
    if (!job?.result_path) return false;
    return jobs.some(candidate => {
      if (candidate.id === job.id) return false;
      const inputs = candidate.parameters?.input_images;
      if (!Array.isArray(inputs)) return false;
      return inputs.some(input => {
        if (!input || typeof input !== 'object') return false;
        const reference = input as { result_path?: unknown; source_result_path?: unknown };
        return [reference.result_path, reference.source_result_path].some(resultPath => typeof resultPath === 'string' && resultPath === job.result_path);
      });
    });
  };
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
    setProviderQueueStates(result.provider_queue_states || []);
    const focusedJob = initialJobId && !initialFocusAppliedRef.current ? nextJobs.find(job => job.id === initialJobId) : undefined;
    const trackedSetId = activeGenerationSet?.generation_group_id
      || focusedJob?.generation_group_id
      || nextJobs.find(job => job.generation_group_id && ['queued', 'running'].includes(job.status))?.generation_group_id;
    const refreshedSet = trackedSetId
      ? (result.generation_sets || []).find(set => set.generation_group_id === trackedSetId)
      : undefined;
    if (refreshedSet) setActiveGenerationSet(refreshedSet);
    if (focusedJob) {
      initialFocusAppliedRef.current = true;
      setActiveJobId(focusedJob.id);
      setFocusedJobHighlightId(focusedJob.id);
      if (!historyReviewJobId) setHistoryReviewJobId(focusedJob.id);
    }
    return nextJobs;
  };

  const refreshGenerationSet = async (generationGroupId: string) => {
    const refreshed = await api.generationSet(generationGroupId);
    setActiveGenerationSet(refreshed);
    setJobs(current => mergeGenerationJobs(current, refreshed.jobs));
    return refreshed;
  };

  useEffect(() => {
    let cancelled = false;
    api.generationProviders()
      .then(nextProviders => {
        if (cancelled) return;
        setProviders(nextProviders);
        const firstReady = nextProviders.find(nextProvider => nextProvider.provider !== 'manual_upload' && providerCanGenerate(nextProvider)) || nextProviders.find(providerCanGenerate) || nextProviders[0];
        if (firstReady) {
          setProvider(firstReady.provider);
          setOrchestratorModel(firstReady.default_orchestrator_model || firstReady.orchestrator_models?.[0] || 'gpt-5.6-luna');
        }
      })
      .catch(() => setProviders([{ provider: 'manual_upload', display_name: 'Manual upload', optional: false, configured: true, authenticated: true, available: true, state: 'available', reason: null, features: { manual_result_upload: true } }]));
    refreshJobs().catch(() => undefined);
    return () => { cancelled = true; };
  }, [item?.id, initialJobId]);

  useEffect(() => {
    setTemplateValues(current => {
      const keys = templateVariables.map(variable => variable.key);
      const next = Object.fromEntries(keys.map(key => [key, current[key] || '']));
      if (Object.keys(current).length === keys.length && keys.every(key => current[key] === next[key])) return current;
      return next;
    });
  }, [templateVariableKeySignature]);

  useEffect(() => {
    if (!initialJobId) return;
    initialFocusAppliedRef.current = false;
    setActiveJobId(initialJobId);
    setFocusedJobHighlightId(initialJobId);
    setHistoryReviewJobId(initialJobId);
  }, [initialJobId]);

  useEffect(() => {
    if (!activeGenerationSet?.remaining && !jobs.some(job => ['queued', 'running'].includes(job.status))) return undefined;
    const refreshActiveWork = async () => {
      await refreshJobs({ preserveActive: true });
      if (activeGenerationSet?.generation_group_id) {
        await refreshGenerationSet(activeGenerationSet.generation_group_id);
      }
    };
    const timer = window.setInterval(() => refreshActiveWork().catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [jobs, item?.id, initialJobId, activeGenerationSet?.generation_group_id, activeGenerationSet?.remaining]);

  useEffect(() => {
    if (!providerQueueStates.some(state => providerPauseSeconds(state) > 0)) return undefined;
    setQueueClock(Date.now());
    const timer = window.setInterval(() => setQueueClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [providerQueueStates]);

  useEffect(() => {
    if (!generationCountMenuOpen || !generationCountFocusOnOpenRef.current) return;
    generationCountFocusOnOpenRef.current = false;
    generationCountMenuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
  }, [generationCountMenuOpen]);

  useEffect(() => {
    if (!generationCountMenuOpen) return undefined;
    const closeOutside = (event: PointerEvent) => {
      if (!generationCountMenuRef.current?.contains(event.target as Node)) setGenerationCountMenuOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [generationCountMenuOpen]);

  const handleGenerationCountMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(generationCountMenuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') || []);
    if (event.key === 'Escape') {
      event.preventDefault();
      setGenerationCountMenuOpen(false);
      generationCountTriggerRef.current?.focus();
      return;
    }
    if (!items.length || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = items.findIndex(item => item === document.activeElement);
    if (event.key === 'Home') items[0].focus();
    else if (event.key === 'End') items[items.length - 1]?.focus();
    else if (event.key === 'ArrowDown') items[(currentIndex + 1 + items.length) % items.length].focus();
    else items[(currentIndex - 1 + items.length) % items.length].focus();
  };

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
    if (!selectedStageJob || !['succeeded', 'failed'].includes(selectedStageJob.status)) return;
    window.requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }, [selectedStageJob?.id, selectedStageJob?.status]);

  const closeStageFullscreen = async () => {
    if (document.fullscreenElement === fullscreenFrameRef.current) {
      await document.exitFullscreen?.();
    }
    setIsStageFullscreen(false);
  };

  const createJob = async (count: GenerationSetCount = 1) => {
    const prompt = promptText.trim();
    if (!prompt || hasMissingTemplateValues || !resolvedPrompt || !selectedProviderCanGenerate || (provider === 'manual_upload' && count !== 1)) return;
    setBusy(true);
    setMessage('');
    setGenerationCountMenuOpen(false);
    setHistoryReviewJobId(undefined);
    window.requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    try {
      const attachments = imageAttachmentPayload();
      const sourcePrompt = defaultPrompt || prompt;
      const jobEditedPromptText = resolvedPrompt === sourcePrompt.trim() ? null : resolvedPrompt;
      const templateParameters = hasTemplateVariables ? {
        prompt_template: prompt,
        prompt_template_values: promptTemplateValues,
        prompt_template_resolved_text: resolvedPrompt,
      } : {};
      const jobPayload: GenerationJobCreate = {
        source_item_id: item?.id,
        mode: attachments.length > 0 ? 'image_edit' : 'text_to_image',
        provider,
        model: provider === 'openai_codex_oauth_native' ? 'gpt-image-2' : null,
        prompt_language: defaultPromptLanguage,
        prompt_text: sourcePrompt,
        edited_prompt_text: jobEditedPromptText,
        reference_image_ids: [],
        parameters: {
          requested_aspect_ratio: aspectRatio,
          aspect_ratio_prompt_injection: aspectRatio !== 'auto',
          quality,
          orchestrator_model: orchestratorModel,
          input_images: attachments,
          ...templateParameters,
        },
      };
      let createdJobs: GenerationJobRecord[];
      if (count === 1) {
        const created = await api.createGenerationJob(jobPayload);
        createdJobs = [created];
        setActiveGenerationSet(undefined);
      } else {
        const createdSet = await api.createGenerationSet({ job: jobPayload, count });
        createdJobs = createdSet.jobs;
        setActiveGenerationSet(createdSet);
      }
      setJobs(current => mergeGenerationJobs(current, createdJobs));
      setActiveJobId(createdJobs[0]?.id);
      window.requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
      setMessage(provider === 'manual_upload'
        ? 'Job created. Upload a generated result when ready.'
        : count > 1
          ? `Generation set queued · ${count} generations.`
          : attachments.length > 0
            ? 'Edit queued. It will start automatically.'
            : 'Generation queued. It will start automatically.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create generation job.');
    } finally {
      setBusy(false);
    }
  };

  const cancelRemainingGenerationSet = async () => {
    if (!activeGenerationSet?.remaining || cancelSetBusy) return;
    setCancelSetBusy(true);
    try {
      const cancelled = await api.cancelRemainingGenerationSet(activeGenerationSet.generation_group_id);
      setActiveGenerationSet(cancelled);
      setJobs(current => mergeGenerationJobs(current, cancelled.jobs));
      setMessage('Remaining generations cancelled. Completed results are still available.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not cancel remaining generations.');
    } finally {
      setCancelSetBusy(false);
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
    image_id: attachment.imageId,
    source_item_id: attachment.sourceItemId,
    role: attachment.role,
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

  const moveAttachment = (index: number, offset: -1 | 1) => {
    setEditAttachments(current => {
      const nextIndex = index + offset;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  };

  const addLibraryAttachment = (image: ImageRecord, title: string) => {
    setEditAttachments(current => {
      if (current.length >= MAX_EDIT_ATTACHMENTS || current.some(attachment => attachment.imageId === image.id)) return current;
      return [...current, libraryAttachment(image, title)];
    });
  };

  const openLibraryPicker = async () => {
    setReferenceMenuOpen(false);
    setReferencePicker('library');
    setLibraryItem(undefined);
    if (libraryItems.length) return;
    setPickerBusy(true);
    try {
      const result = await api.items({ limit: 1000, sort: 'updated_desc' });
      setLibraryItems(result.items.filter(candidate => candidate.first_image));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load library images.');
      setReferencePicker(null);
    } finally {
      setPickerBusy(false);
    }
  };

  const openLibraryItem = async (candidate: ItemSummary) => {
    setPickerBusy(true);
    try {
      setLibraryItem(await api.item(candidate.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load library item.');
    } finally {
      setPickerBusy(false);
    }
  };

  const openRecentPicker = async () => {
    setReferenceMenuOpen(false);
    setReferencePicker('recent');
    setPickerBusy(true);
    try {
      const result = await api.generationJobs({ limit: 100 });
      setRecentJobs(result.jobs.filter(candidate => Boolean(candidate.result_path) && ['succeeded', 'accepted'].includes(candidate.status)));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load recent generation results.');
      setReferencePicker(null);
    } finally {
      setPickerBusy(false);
    }
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
      setOrchestratorModel(jobModel(result.retry_job));
      setEditAttachments(restorableJobAttachments(result.retry_job));
      setFocusedJobHighlightId(result.retry_job.id);
      setMessage('Retry queued.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not retry job.');
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const retryFailedJob = async (job: GenerationJobRecord) => {
    if (!canRetryFailedJob(job)) {
      const retryId = retriedByJobId(job);
      if (retryId) {
        setActiveJobId(retryId);
        setHistoryReviewJobId(undefined);
        setFocusedJobHighlightId(retryId);
      }
      return;
    }
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const retry = await api.retryGenerationJob(job.id);
      setJobs(current => [retry, ...current.filter(candidate => candidate.id !== retry.id)]);
      setActiveJobId(retry.id);
      setHistoryReviewJobId(undefined);
      setPromptText(jobPrompt(retry));
      setAspectRatio(jobAspectRatio(retry));
      setQuality(jobQuality(retry));
      setProvider(retry.provider || provider);
      setOrchestratorModel(jobModel(retry));
      setEditAttachments(restorableJobAttachments(retry));
      setFocusedJobHighlightId(retry.id);
      setMessage('Generation job retried.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not retry failed job.');
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const markStaleRunningJobFailed = async (job: GenerationJobRecord) => {
    if (!isStaleRunningJob(job)) return;
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const updated = await api.markGenerationJobFailed(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setHistoryReviewJobId(undefined);
      setMessage('Generation job marked failed.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not mark stale job failed.');
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
    const attachments = jobAttachments(job);
    const restorableAttachments = restorableJobAttachments(job);
    setPromptText(jobPrompt(job));
    setAspectRatio(jobAspectRatio(job));
    setQuality(jobQuality(job));
    setProvider(job.provider || provider);
    setOrchestratorModel(jobModel(job));
    setEditAttachments(restorableAttachments);
    setHistoryReviewJobId(undefined);
    setMessage(attachments.length > restorableAttachments.length ? 'Prompt copied. Re-upload unavailable image references before generating.' : 'Prompt copied to draft.');
    window.requestAnimationFrame(() => {
      promptInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      promptInputRef.current?.focus({ preventScroll: true });
    });
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

  const renderReferenceTray = (attachments: EditAttachment[], readOnly = false) => (
    <div className={`generation-reference-tray${readOnly ? ' is-readonly' : ''}`} aria-label={readOnly ? 'References used' : 'Generation references'}>
      <div className="generation-reference-tray-head">
        <strong>{readOnly ? 'References used' : 'References'}</strong>
        <span>{attachments.length} / {MAX_EDIT_ATTACHMENTS}</span>
      </div>
      <div className="generation-reference-items">
        {attachments.map((attachment, index) => (
          <div className="generation-reference-card" key={attachment.id} title={attachment.name}>
            <span className="generation-reference-number">{index + 1}</span>
            {attachment.previewUrl ? <img src={attachment.previewUrl} alt="" loading="lazy" /> : <span className="generation-reference-placeholder"><Images size={15} /></span>}
            <span className="generation-reference-copy">
              <b>{attachment.source === 'library' ? 'Library' : attachment.source === 'generated_result' ? 'Generated' : 'Upload'}</b>
              <em>{attachment.name}</em>
            </span>
            {!readOnly && (
              <span className="generation-reference-actions">
                <button type="button" onClick={() => moveAttachment(index, -1)} disabled={index === 0} aria-label={`Move ${attachment.name} left`}><ChevronLeft size={13} /></button>
                <button type="button" onClick={() => moveAttachment(index, 1)} disabled={index === attachments.length - 1} aria-label={`Move ${attachment.name} right`}><ChevronRight size={13} /></button>
                <button type="button" onClick={() => removeAttachment(attachment.id)} aria-label={`Remove ${attachment.name}`}><X size={13} /></button>
              </span>
            )}
          </div>
        ))}
        {!readOnly && attachments.length < MAX_EDIT_ATTACHMENTS && (
          <div className="generation-reference-add-wrap">
            <button type="button" className="generation-reference-add" onClick={() => setReferenceMenuOpen(current => !current)} aria-label="Add generation reference"><Plus size={16} /> Add</button>
          </div>
        )}
      </div>
      {!readOnly && referenceMenuOpen && (
        <div className="generation-reference-source-menu">
          <button type="button" onClick={() => { setReferenceMenuOpen(false); attachmentInputRef.current?.click(); }}><Upload size={15} /> Upload image</button>
          <button type="button" onClick={() => openLibraryPicker().catch(() => undefined)}><Images size={15} /> Choose from library</button>
          <button type="button" onClick={() => openRecentPicker().catch(() => undefined)}><Clock3 size={15} /> Choose recent result</button>
        </div>
      )}
    </div>
  );

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
      {canDiscardTransientResult(job) && (
        <button className="stage-action danger" onClick={() => discardJob(job)} disabled={busy} aria-label="Discard" title="Discard">
          <Trash2 size={16} aria-hidden="true" />
        </button>
      )}
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
          {isStaleRunningJob(selectedStageJob) && (
            <div className="generation-stage-actions" aria-label="Stale generation actions">
              <p className="generation-stale-copy">Generation may have stalled. Mark failed to retry.</p>
              <button className="stage-action" onClick={() => markStaleRunningJobFailed(selectedStageJob)} disabled={busy} aria-label="Mark failed to retry" title="Mark failed to retry">
                Mark failed
              </button>
            </div>
          )}
        </div>
      );
    }
    if (selectedStageJob.status === 'failed') {
      const retryId = retriedByJobId(selectedStageJob);
      const failure = generationFailure(selectedStageJob);
      const retryButton = canRetryFailedJob(selectedStageJob) ? (
        <button className={`stage-action${failure.kind === 'policy_violation' || failure.kind === 'auth_required' ? '' : ' primary'}`} onClick={() => retryFailedJob(selectedStageJob)} disabled={busy}>
          Retry
        </button>
      ) : null;
      const editPromptButton = (
        <button className={`stage-action${failure.kind === 'policy_violation' ? ' primary' : ''}`} onClick={() => useJobAsDraft(selectedStageJob)} disabled={busy}>
          Edit prompt
        </button>
      );
      return (
        <div className="generation-stage generation-stage-error">
          <div className="generation-failure-content">
            <div className="generation-failure-announcement" role="alert">
              <strong>{retryId ? 'Retried' : failure.title}</strong>
              <p>{failure.guidance}</p>
              {message && <p className="provider-message generation-failure-message">{message}</p>}
            </div>
            {selectedStageJob.error && (
              <details className="generation-failure-details">
                <summary>Provider details</summary>
                <small>{selectedStageJob.error}</small>
              </details>
            )}
          </div>
          <div className="generation-stage-actions generation-failure-actions" aria-label="Failed generation actions">
            {retryId ? (
              <button className="stage-action primary" onClick={() => retryFailedJob(selectedStageJob)} disabled={busy}>
                Open retry job
              </button>
            ) : (
              <>
                {failure.kind === 'policy_violation' && editPromptButton}
                {failure.kind === 'auth_required' && (
                  <button className="stage-action primary" onClick={onOpenProviders} disabled={busy}>
                    Open Providers
                  </button>
                )}
                {retryButton}
                {failure.kind === 'unknown' && editPromptButton}
              </>
            )}
          </div>
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
        <strong>{statusLabel(selectedStageJob.status, isUsedAsGenerationReference(selectedStageJob))}</strong>
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
                <div className="generation-prompt-area">
                  <textarea ref={promptInputRef} value={promptText} onChange={event => setPromptText(event.currentTarget.value)} placeholder="Prompt" aria-label="Generation prompt" />
                  {renderReferenceTray(editAttachments)}
                </div>
                {hasTemplateVariables && (
                  <div className="generation-template-variable-fields" aria-label="Prompt variables">
                    <div className="generation-template-head">
                      <span>Prompt variables</span>
                      <em>Fill these before generating.</em>
                    </div>
                    <div className="generation-template-grid">
                      {templateVariables.map(variable => (
                        <label key={variable.key} className="generation-template-variable-field">
                          <span>{variable.key}</span>
                          <input
                            value={templateValues[variable.key] || ''}
                            onChange={event => {
                              const value = event.currentTarget.value;
                              setTemplateValues(current => ({ ...current, [variable.key]: value }));
                            }}
                            placeholder={`Value for ${variable.key}`}
                          />
                        </label>
                      ))}
                    </div>
                    <div className="generation-template-preview">
                      <span>Final prompt</span>
                      <p>{resolvedPrompt || 'Complete all variables to preview the final prompt.'}</p>
                    </div>
                  </div>
                )}
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
                  <span className={`generation-provider-readiness ${selectedProviderCanGenerate ? 'is-ready' : 'needs-attention'}`} title={selectedProviderMessage} aria-label={selectedProviderMessage}>
                    {compactProviderMessage}
                  </span>
                  <div
                    ref={generationCountMenuRef}
                    className={`generation-generate-split${provider === 'manual_upload' ? ' is-single' : ''}`}
                    onMouseEnter={() => {
                      generationCountFocusOnOpenRef.current = false;
                      if (provider !== 'manual_upload' && window.matchMedia('(hover: hover)').matches) setGenerationCountMenuOpen(true);
                    }}
                    onMouseLeave={() => setGenerationCountMenuOpen(false)}
                    onKeyDown={handleGenerationCountMenuKeyDown}
                    onBlur={event => {
                      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setGenerationCountMenuOpen(false);
                    }}
                  >
                    <button
                      className="primary generation-primary-action"
                      type="button"
                      onClick={() => createJob(1)}
                      disabled={busy || !selectedProviderCanGenerate || !promptText.trim() || hasMissingTemplateValues}
                      aria-label="Generate 1 image; uses 1 generation"
                    >Generate</button>
                    {provider !== 'manual_upload' && (
                      <button
                        ref={generationCountTriggerRef}
                        className="primary generation-count-trigger"
                        type="button"
                        aria-label="Choose number of generations"
                        aria-haspopup="menu"
                        aria-expanded={generationCountMenuOpen}
                        aria-controls="generation-count-menu"
                        onClick={() => {
                          generationCountFocusOnOpenRef.current = true;
                          setGenerationCountMenuOpen(open => !open);
                        }}
                        onKeyDown={event => {
                          if (!['ArrowDown', 'Enter', ' '].includes(event.key)) return;
                          event.preventDefault();
                          generationCountFocusOnOpenRef.current = true;
                          setGenerationCountMenuOpen(true);
                        }}
                        disabled={busy || !selectedProviderCanGenerate || !promptText.trim() || hasMissingTemplateValues}
                      ><ChevronDown size={17} aria-hidden="true" /></button>
                    )}
                    {generationCountMenuOpen && provider !== 'manual_upload' && (
                      <div id="generation-count-menu" className="generation-count-menu" role="menu" aria-label="Generate variations">
                        {GENERATION_SET_OPTIONS.map(count => (
                          <button key={count} type="button" role="menuitem" onClick={() => createJob(count)}>
                            <strong>Generate ×{count}</strong>
                            <small>Uses {count} generations</small>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <button className="generation-history-control" onClick={() => setShowHistoryDrawer(true)} aria-label="History" title="History" type="button"><Clock3 size={17} /></button>
                </div>
                {selectedProviderQueueState && selectedProviderPauseSeconds > 0 && (
                  <section className="generation-provider-pause" aria-label={`Provider queue paused until ${selectedProviderQueueState.paused_until}`}>
                    <strong>Provider queue paused</strong>
                    <span aria-hidden="true">Rate limited · resumes in about {selectedProviderPauseSeconds}s</span>
                    {selectedProviderQueueState.paused_until && <time className="sr-only" dateTime={selectedProviderQueueState.paused_until}>Paused until {selectedProviderQueueState.paused_until}</time>}
                  </section>
                )}
                {activeGenerationSet && (
                  <section className="generation-set-progress" aria-live="polite">
                    <div className="generation-set-progress-head">
                      <strong>Generation set</strong>
                      <span>{activeGenerationSet.completed} / {activeGenerationSet.total} finished</span>
                    </div>
                    <progress max={activeGenerationSet.total} value={activeGenerationSet.completed} aria-label={`${activeGenerationSet.completed} of ${activeGenerationSet.total} generations finished`} />
                    <p>{generationSetProgressText(activeGenerationSet)}</p>
                    {activeGenerationSet.remaining > 0 && (
                      <button type="button" className="generation-cancel-remaining" onClick={cancelRemainingGenerationSet} disabled={cancelSetBusy}>
                        Cancel remaining ({activeGenerationSet.remaining})
                      </button>
                    )}
                  </section>
                )}
              </>
            ) : historyReviewJob && (
              <div className="generation-history-prompt-preview">
                <textarea readOnly value={jobPrompt(historyReviewJob)} aria-label="Selected history prompt" />
                {renderReferenceTray(jobAttachments(historyReviewJob), true)}
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

        {referencePicker && createPortal((
          <div className="generation-reference-picker-backdrop" onClick={() => setReferencePicker(null)} onKeyDown={event => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            setReferencePicker(null);
          }}>
            <section className="generation-reference-picker" role="dialog" aria-modal="true" aria-label={referencePicker === 'library' ? 'Choose images from library' : 'Choose recent generation result'} onClick={event => event.stopPropagation()} tabIndex={-1} autoFocus>
              <div className="drawer-head">
                <div>
                  <p className="drawer-eyebrow">References · {editAttachments.length} / {MAX_EDIT_ATTACHMENTS}</p>
                  <h3>{referencePicker === 'library' ? 'Choose from library' : 'Choose recent result'}</h3>
                </div>
                <button className="modal-icon-button" type="button" onClick={() => setReferencePicker(null)} aria-label="Close reference picker"><X size={20} /></button>
              </div>
              {pickerBusy && <p className="muted">Loading…</p>}
              {referencePicker === 'library' && !libraryItem && (
                <>
                  <input className="generation-reference-search" value={libraryQuery} onChange={event => setLibraryQuery(event.currentTarget.value)} placeholder="Search library" aria-label="Search library references" />
                  <div className="generation-reference-picker-grid">
                    {libraryItems.filter(candidate => candidate.title.toLowerCase().includes(libraryQuery.trim().toLowerCase())).map(candidate => (
                      <button type="button" className="generation-reference-picker-card" key={candidate.id} onClick={() => openLibraryItem(candidate).catch(() => undefined)}>
                        {candidate.first_image && <img src={mediaUrl(candidate.first_image.preview_path || candidate.first_image.thumb_path || candidate.first_image.original_path)} alt="" loading="lazy" />}
                        <span><b>{candidate.title}</b><em>Choose image</em></span>
                      </button>
                    ))}
                  </div>
                </>
              )}
              {referencePicker === 'library' && libraryItem && (
                <>
                  <button className="generation-reference-back" type="button" onClick={() => setLibraryItem(undefined)}><ArrowLeft size={15} /> Back to library</button>
                  <h4>{libraryItem.title}</h4>
                  <div className="generation-reference-picker-grid images">
                    {libraryItem.images.map(image => {
                      const selected = editAttachments.some(attachment => attachment.imageId === image.id);
                      return (
                        <button type="button" className={`generation-reference-picker-card${selected ? ' is-selected' : ''}`} key={image.id} onClick={() => addLibraryAttachment(image, libraryItem.title)} disabled={selected || editAttachments.length >= MAX_EDIT_ATTACHMENTS}>
                          <img src={mediaUrl(image.preview_path || image.thumb_path || image.original_path)} alt="" loading="lazy" />
                          <span><b>{image.role === 'reference_image' ? 'Reference' : 'Result'}</b><em>{selected ? 'Selected' : 'Add reference'}</em></span>
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
              {referencePicker === 'recent' && (
                <div className="generation-reference-picker-grid">
                  {recentJobs.map(job => {
                    const selected = editAttachments.some(attachment => attachment.resultPath === job.result_path);
                    return (
                      <button type="button" className={`generation-reference-picker-card${selected ? ' is-selected' : ''}`} key={job.id} onClick={() => addResultAsAttachment(job)} disabled={selected || editAttachments.length >= MAX_EDIT_ATTACHMENTS}>
                        {job.result_path && <img src={jobResultUrl(job)} alt="" loading="lazy" />}
                        <span><b>{jobPrompt(job) || 'Generated result'}</b><em>{selected ? 'Selected' : job.id}</em></span>
                      </button>
                    );
                  })}
                  {!pickerBusy && recentJobs.length === 0 && <p className="muted">No recent results available.</p>}
                </div>
              )}
              <div className="generation-reference-picker-footer">
                <button className="primary" type="button" onClick={() => setReferencePicker(null)}>Done · {editAttachments.length} selected</button>
              </div>
            </section>
          </div>
        ), document.body)}

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
              <button key={job.id} className={`generation-history-item status-${job.status}`} onClick={() => previewHistoryJob(job)} aria-label={`${statusLabel(job.status, isUsedAsGenerationReference(job))} generation, ${jobAspectRatio(job)}, ${jobQuality(job)}, ${jobModel(job)}`}>
                <span className="generation-history-media">
                  {jobResultUrl(job) ? <img src={jobResultUrl(job)} alt="" /> : <span className="generation-history-placeholder">{statusLabel(job.status, isUsedAsGenerationReference(job))}</span>}
                </span>
                <span className="generation-history-status-grid" aria-hidden="true">
                  <span className="generation-history-cell"><b>Aspect ratio</b><em>{optionLabel(ASPECT_RATIO_OPTIONS, jobAspectRatio(job))}</em></span>
                  <span className="generation-history-cell"><b>Quality</b><em>{optionLabel(QUALITY_OPTIONS, jobQuality(job))}</em></span>
                  <span className="generation-history-cell"><b>Model</b><em>{jobModel(job)}</em></span>
                  <span className="generation-history-cell"><b>Status</b><em>{statusLabel(job.status, isUsedAsGenerationReference(job))}</em></span>
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
                {renderReferenceTray(jobAttachments(reviewJob), true)}
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
