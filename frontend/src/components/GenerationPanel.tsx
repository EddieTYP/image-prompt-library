import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, ChevronDown, ChevronLeft, ChevronRight, Clipboard, Clock3, Download, FilePlus2, Images, Maximize2, Paperclip, Plus, RotateCcw, Trash2, Upload, X } from 'lucide-react';
import aspectRatioIcon from '../assets/generation-controls/aspect-ratio.png';
import brainAiIcon from '../assets/generation-controls/model.png';
import qualityIcon from '../assets/generation-controls/quality.png';
import { api, mediaUrl } from '../api/client';
import type { ClusterRecord, GenerationJobAcceptAsNewItemPayload, GenerationJobCreate, GenerationJobRecord, GenerationJobSetRecord, GenerationProviderQueueState, GenerationProviderStatus, GenerationSetCount, ImageRecord, ItemDetail, ItemSummary, TagRecord } from '../types';
import type { Translator } from '../utils/i18n';
import { providerPauseSeconds } from '../utils/generationSets';
import { downloadFileName } from '../utils/images';
import { generationFailure } from '../utils/generationFailures';
import { resolveOriginalPrompt, resolvePromptText, type PromptCopyLanguage } from '../utils/prompts';
import { extractPromptTemplateVariableRecords, resolvePromptTemplate } from '../utils/promptTemplateVariables';
import { createGenerationReviewSession, generationResultPosition, generationReviewNext, generationReviewOpenContext, generationReviewSlotNavigation, generationReviewSummary, generationSiblingNavigation, isActionableGenerationResult, mapGenerationRetryJobs, mapGenerationRetryToReviewSlot, reconcileGenerationReviewSession, resolveGenerationReviewSlot, retainPendingRetryJobIds, type GenerationReviewSession } from '../utils/generationSiblings';
import { useModalFocus } from '../hooks/useModalFocus';
import SuggestedTitleField from './SuggestedTitleField';

function providerReady(provider: GenerationProviderStatus) {
  return Boolean(provider.available && provider.authenticated && provider.configured);
}

function providerCanGenerate(provider?: GenerationProviderStatus) {
  if (!provider) return false;
  return provider.can_generate ?? providerReady(provider);
}

function providerReadinessLabel(provider: GenerationProviderStatus | undefined, t: Translator) {
  if (!provider) return t('providerUnavailable');
  if (providerCanGenerate(provider)) return t('providerReady').replace('${provider}', provider.display_name);
  if (provider.status === 'login_required' || provider.state === 'not_connected') return t('connectProvider').replace('${provider}', provider.display_name);
  if (provider.status === 'auth_error') return t('providerNeedsAttention').replace('${provider}', provider.display_name);
  if (provider.message) return provider.message;
  return t('providerUnavailableForGeneration').replace('${provider}', provider.display_name);
}

function compactProviderReadinessLabel(provider: GenerationProviderStatus | undefined, t: Translator) {
  if (providerCanGenerate(provider)) return t('generationReady');
  return providerReadinessLabel(provider, t);
}

function statusLabel(status: string, t: Translator, isUsedAsGenerationReference = false) {
  if (status === 'queued') return t('queueQueued');
  if (status === 'running') return t('queueRunning');
  if (status === 'succeeded') return isUsedAsGenerationReference ? t('queueUsedAsReference') : t('queueReady');
  if (status === 'accepted') return t('queueSaved');
  if (status === 'discarded') return t('queueDiscarded');
  if (status === 'cancelled') return t('queueCancelled');
  if (status === 'failed') return t('queueFailed');
  return status;
}

function jobResultUrl(job: GenerationJobRecord) {
  return job.result_path && !['discarded', 'cancelled', 'failed'].includes(job.status) ? mediaUrl(job.result_path) : '';
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
const MAX_OPEN_CONTEXT_ACTIVE_FETCHES = 16;
const HISTORY_FOCUSABLE_SELECTOR = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const SAVE_NEW_LANGUAGE_OPTIONS = [
  { value: 'en', labelKey: 'englishPrompt' },
  { value: 'zh_hant', labelKey: 'traditionalChinesePrompt' },
  { value: 'zh_hans', labelKey: 'simplifiedChinesePrompt' },
] as const;

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
  const position = generationResultPosition(job);
  const titleSuffix = position ? ` Variant ${position.index}` : ' Variant';
  return {
    title: item ? `${item.title}${titleSuffix}` : `Generated image${position ? titleSuffix : ''}`,
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

function optionLabel(options: { value: string; label: string }[], value: string, t: Translator) {
  if (value === 'auto') return t('generationAuto');
  if (value === 'low') return t('generationLow');
  if (value === 'medium') return t('generationMedium');
  if (value === 'high') return t('generationHigh');
  return options.find(option => option.value === value)?.label || value;
}

function localizedGenerationSetProgressText(set: GenerationJobSetRecord, t: Translator) {
  const parts = [t('finished').replace('${completed}', String(set.completed)).replace('${total}', String(set.total))];
  if (set.running) parts.push(`${set.running} ${t('queueRunning')}`);
  if (set.queued) parts.push(`${set.queued} ${t('queueQueued')}`);
  if (set.succeeded) parts.push(`${set.succeeded} ${t('queueReady')}`);
  if (set.failed) parts.push(`${set.failed} ${t('queueFailed')}`);
  if (set.cancelled) parts.push(`${set.cancelled} ${t('queueCancelled')}`);
  return parts.join(' · ');
}

function scrollIntoViewRespectingMotion(element: HTMLElement | null, block: ScrollLogicalPosition) {
  if (!element) return;
  const behavior: ScrollBehavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  element.scrollIntoView({ behavior, block });
}

function watchMotionEnd(element: HTMLElement | null, callback: () => void) {
  if (!element || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    callback();
    return () => undefined;
  }
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    element.removeEventListener('animationend', handleAnimationEnd);
    element.removeEventListener('transitionend', handleTransitionEnd);
    window.clearTimeout(fallback);
    callback();
  };
  const handleAnimationEnd = (event: AnimationEvent) => {
    if (event.target === element) finish();
  };
  const handleTransitionEnd = (event: TransitionEvent) => {
    if (event.target === element) finish();
  };
  element.addEventListener('animationend', handleAnimationEnd);
  element.addEventListener('transitionend', handleTransitionEnd);
  const fallback = window.setTimeout(finish, 260);
  return () => {
    if (finished) return;
    finished = true;
    element.removeEventListener('animationend', handleAnimationEnd);
    element.removeEventListener('transitionend', handleTransitionEnd);
    window.clearTimeout(fallback);
  };
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
  onQueueChanged,
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
  onQueueChanged?: () => void;
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
  const [provider, setProvider] = useState('openai_codex_oauth_native');
  const [orchestratorModel, setOrchestratorModel] = useState('gpt-5.6-terra');
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
  const [isHistoryDrawerClosing, setIsHistoryDrawerClosing] = useState(false);
  const [historyReviewJobId, setHistoryReviewJobId] = useState<string | undefined>(initialJobId);
  const [batchReviewSession, setBatchReviewSession] = useState<GenerationReviewSession>();
  const [batchReviewPaused, setBatchReviewPaused] = useState(false);
  const [pendingRetryJobIds, setPendingRetryJobIds] = useState<string[]>([]);
  const [isClosing, setIsClosing] = useState(false);
  const [isStageFullscreen, setIsStageFullscreen] = useState(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onAcceptedRef = useRef(onAccepted);
  onAcceptedRef.current = onAccepted;
  const onQueueChangedRef = useRef(onQueueChanged);
  onQueueChangedRef.current = onQueueChanged;
  const pendingAcceptedRef = useRef<{ item?: ItemDetail; message?: string } | undefined>(undefined);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const metadataPanelRef = useRef<HTMLElement | null>(null);
  const focusedJobRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLElement | null>(null);
  const resultImageRef = useRef<HTMLImageElement | null>(null);
  const fullscreenFrameRef = useRef<HTMLDivElement | null>(null);
  const fullscreenTriggerRef = useRef<HTMLButtonElement | null>(null);
  const fullscreenCloseRef = useRef<HTMLButtonElement | null>(null);
  const fullscreenWasOpenRef = useRef(false);
  const generationCountMenuRef = useRef<HTMLDivElement | null>(null);
  const generationCountTriggerRef = useRef<HTMLButtonElement | null>(null);
  const generationCountFocusOnOpenRef = useRef(false);
  const generationCountCloseTimerRef = useRef<number | undefined>(undefined);
  const controlTriggerRefs = useRef<Record<'aspect' | 'quality' | 'model', HTMLButtonElement | null>>({ aspect: null, quality: null, model: null });
  const referenceAddTriggerRef = useRef<HTMLButtonElement | null>(null);
  const referenceAddWrapRef = useRef<HTMLDivElement | null>(null);
  const historyTriggerRef = useRef<HTMLButtonElement | null>(null);
  const historyDrawerRef = useRef<HTMLElement | null>(null);
  const libraryItemBackRef = useRef<HTMLButtonElement | null>(null);
  const librarySearchRef = useRef<HTMLInputElement | null>(null);
  const libraryItemRequestRef = useRef(0);
  const saveAsNewTriggerRef = useRef<HTMLButtonElement | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const promptInputRef = useRef<HTMLTextAreaElement | null>(null);
  const initialFocusAppliedRef = useRef(false);
  const jobsRequestRef = useRef(0);
  const generationSetRequestRef = useRef(0);
  const jobsRef = useRef<GenerationJobRecord[]>(jobs);
  const batchReviewCursorJobIdRef = useRef<string | undefined>(initialJobId);
  jobsRef.current = jobs;

  const clearGenerationCountCloseTimer = () => {
    if (generationCountCloseTimerRef.current === undefined) return;
    window.clearTimeout(generationCountCloseTimerRef.current);
    generationCountCloseTimerRef.current = undefined;
  };
  const scheduleGenerationCountClose = () => {
    clearGenerationCountCloseTimer();
    generationCountCloseTimerRef.current = window.setTimeout(() => {
      generationCountCloseTimerRef.current = undefined;
      setGenerationCountMenuOpen(false);
    }, 140);
  };

  const invalidateGenerationSetRequest = () => {
    generationSetRequestRef.current += 1;
  };

  const invalidateGenerationRefreshRequests = () => {
    jobsRequestRef.current += 1;
    generationSetRequestRef.current += 1;
  };

  const replaceGenerationJobs = (nextJobs: GenerationJobRecord[]) => {
    jobsRef.current = nextJobs;
    setJobs(nextJobs);
    return nextJobs;
  };

  const updateGenerationJobs = (update: (current: GenerationJobRecord[]) => GenerationJobRecord[]) => (
    replaceGenerationJobs(update(jobsRef.current))
  );

  const setActiveGenerationSetSafely = (next?: GenerationJobSetRecord) => {
    invalidateGenerationSetRequest();
    setActiveGenerationSet(next);
  };

  const activeJob = useMemo(() => jobs.find(job => job.id === activeJobId), [jobs, activeJobId]);
  const historyReviewJob = useMemo(() => jobs.find(job => job.id === historyReviewJobId), [jobs, historyReviewJobId]);
  const visibleJobs = useMemo(() => jobs, [jobs]);
  const selectedStageJob = useMemo(() => {
    const candidate = historyReviewJob || activeJob;
    if (!candidate) return undefined;
    const slot = batchReviewSession?.slots.find(reviewSlot => reviewSlot.currentJobId === candidate.id || reviewSlot.originalJobId === candidate.id);
    if (slot?.resultPath && !candidate.result_path && !['discarded', 'cancelled', 'failed'].includes(candidate.status)) return { ...candidate, result_path: slot.resultPath };
    return candidate;
  }, [activeJob, batchReviewSession, historyReviewJob]);
  const siblingNavigation = useMemo(() => generationSiblingNavigation(visibleJobs, selectedStageJob), [visibleJobs, selectedStageJob]);
  const batchReviewSummary = useMemo(
    () => batchReviewSession ? generationReviewSummary(jobs, batchReviewSession, pendingRetryJobIds) : undefined,
    [batchReviewSession, jobs, pendingRetryJobIds],
  );
  const batchReviewActive = Boolean(batchReviewSession);
  const selectedProvider = useMemo(() => providers.find(candidate => candidate.provider === provider), [providers, provider]);
  const selectedProviderCanGenerate = providerCanGenerate(selectedProvider);
  const selectedProviderMessage = providerReadinessLabel(selectedProvider, t);
  const compactProviderMessage = compactProviderReadinessLabel(selectedProvider, t);
  const selectedProviderQueueState = providerQueueStates.find(state => state.provider === provider);
  const selectedProviderPauseSeconds = selectedProviderQueueState ? providerPauseSeconds(selectedProviderQueueState, queueClock) : 0;
  const orchestratorModels = selectedProvider?.orchestrator_models || ['gpt-5.6-terra', 'gpt-5.6-sol', 'gpt-5.6-luna'];
  const recommendedOrchestratorModel = selectedProvider?.default_orchestrator_model || orchestratorModels[0];
  const orchestratorModelLabel = (model: string) => model === recommendedOrchestratorModel ? `${t('generationRecommended')} · ${model}` : model;
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
  const ensureBatchReviewSession = (job?: GenerationJobRecord) => {
    if (!job?.generation_group_id || (job.generation_group_size || 1) <= 1) return undefined;
    batchReviewCursorJobIdRef.current = job.id;
    const existing = batchReviewSession;
    if (existing?.generationGroupId === job.generation_group_id) return existing;
    const created = createGenerationReviewSession(jobsRef.current, job);
    if (created) {
      setBatchReviewSession(created);
      setBatchReviewPaused(false);
      setPendingRetryJobIds([]);
    }
    return created;
  };
  const reviewJobForSlot = (session: GenerationReviewSession, job?: GenerationJobRecord) => {
    if (!job) return undefined;
    return session.slots.find(slot => slot.currentJobId === job.id || slot.originalJobId === job.id);
  };
  const advanceBatchReview = (job: GenerationJobRecord, nextSession?: GenerationReviewSession, sourceJobs?: GenerationJobRecord[]) => {
    const session = nextSession || batchReviewSession;
    if (!session) return false;
    batchReviewCursorJobIdRef.current = job.id;
    const nextJob = generationReviewNext(sourceJobs || jobsRef.current, session, job.id);
    setBatchReviewPaused(false);
    if (nextJob) {
      batchReviewCursorJobIdRef.current = nextJob.id;
      setActiveJobId(nextJob.id);
      setHistoryReviewJobId(nextJob.id);
      setFocusedJobHighlightId(nextJob.id);
      return true;
    }
    // Keep the resolved result on stage after the final actionable slot. The
    // stable slot remains selectable for navigation and its outcome state is
    // rendered without clearing the image.
    setHistoryReviewJobId(job.id);
    setActiveJobId(job.id);
    setFocusedJobHighlightId(job.id);
    return false;
  };
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
    const requestId = jobsRequestRef.current + 1;
    jobsRequestRef.current = requestId;
    const generationSetRequestId = generationSetRequestRef.current + 1;
    generationSetRequestRef.current = generationSetRequestId;
    const openContext = generationReviewOpenContext(initialJobId);
    const contextHydrationFailedIds = new Set<string>();
    const result = await api.generationJobs({ limit: 100, source_item_id: item?.id });
    if (jobsRequestRef.current !== requestId) return undefined;
    let nextJobs = mapGenerationRetryJobs(item ? result.jobs : result.jobs.filter(job => !job.source_item_id));
    if (openContext?.jobs.length) {
      const scopedContextJobs = item ? openContext.jobs.filter(job => job.source_item_id === item.id) : openContext.jobs.filter(job => !job.source_item_id);
      const contextJobs = mapGenerationRetryJobs(scopedContextJobs);
      const freshJobsById = new Map(nextJobs.map(job => [job.id, job]));
      const activeContextJobsMissingFromPage = contextJobs
        .filter(contextJob => ['queued', 'running'].includes(contextJob.status) && !freshJobsById.has(contextJob.id))
        .slice(0, MAX_OPEN_CONTEXT_ACTIVE_FETCHES);
      const activeContextFetchIds = new Set(activeContextJobsMissingFromPage.map(contextJob => contextJob.id));
      const fetchedContextJobs = await Promise.all(activeContextJobsMissingFromPage.map(async contextJob => {
        try {
          const fetchedJob = mapGenerationRetryJobs([await api.generationJob(contextJob.id)])[0];
          return fetchedJob ? [fetchedJob] as const : [];
        } catch {
          contextHydrationFailedIds.add(contextJob.id);
          return [] as const;
        }
      }));
      if (jobsRequestRef.current !== requestId) return undefined;
      const fetchedJobsById = new Map(fetchedContextJobs.flat().map(job => [job.id, job]));
      const hydratedContextJobs = contextJobs.flatMap(contextJob => {
        const freshJob = freshJobsById.get(contextJob.id) || fetchedJobsById.get(contextJob.id);
        if (!freshJob && ['queued', 'running'].includes(contextJob.status) && activeContextFetchIds.has(contextJob.id)) return [];
        return freshJob ? {
          ...freshJob,
          generation_group_id: freshJob.generation_group_id || contextJob.generation_group_id,
          generation_group_index: freshJob.generation_group_index || contextJob.generation_group_index,
          generation_group_size: freshJob.generation_group_size || contextJob.generation_group_size,
        } : contextJob;
      });
      nextJobs = mergeGenerationJobs(nextJobs, hydratedContextJobs);
    }
    let focusedJob = initialJobId && !initialFocusAppliedRef.current ? nextJobs.find(job => job.id === initialJobId) : undefined;
    let focusedSet: GenerationJobSetRecord | undefined;
    if (initialJobId && !initialFocusAppliedRef.current && !focusedJob && !contextHydrationFailedIds.has(initialJobId)) {
      try {
        const fetchedJob = await api.generationJob(initialJobId);
        if (jobsRequestRef.current !== requestId) return undefined;
        const belongsToScope = item ? fetchedJob.source_item_id === item.id : !fetchedJob.source_item_id;
        if (belongsToScope) {
          const mappedFetchedJob = mapGenerationRetryJobs([fetchedJob])[0];
          if (!mappedFetchedJob) return undefined;
          focusedJob = mappedFetchedJob;
          nextJobs = mergeGenerationJobs(nextJobs, [mappedFetchedJob]);
          if (mappedFetchedJob.generation_group_id) {
            focusedSet = await api.generationSet(mappedFetchedJob.generation_group_id);
            if (jobsRequestRef.current !== requestId || generationSetRequestRef.current !== generationSetRequestId) return undefined;
            nextJobs = mergeGenerationJobs(nextJobs, mapGenerationRetryJobs(focusedSet.jobs));
          }
        }
      } catch {
        // The queue can contain a job that was removed after the drawer loaded.
      }
    }
    if (options.preserveActive) {
      const preservedIds = new Set([
        activeJobId,
        historyReviewJobId,
        reviewJob?.id,
        ...((batchReviewSession?.slots || []).map(slot => slot.currentJobId)),
      ].filter((id): id is string => Boolean(id)));
      const preservedJobs = jobsRef.current.filter(job => preservedIds.has(job.id) && !contextHydrationFailedIds.has(job.id));
      nextJobs = mergeGenerationJobs(preservedJobs, nextJobs);
    }
    replaceGenerationJobs(nextJobs);
    setProviderQueueStates(result.provider_queue_states || []);
    const trackedSetId = activeGenerationSet?.generation_group_id
      || focusedJob?.generation_group_id
      || nextJobs.find(job => job.generation_group_id && ['queued', 'running'].includes(job.status))?.generation_group_id;
    const refreshedSet = focusedSet || (trackedSetId
      ? (result.generation_sets || []).find(set => set.generation_group_id === trackedSetId)
      : undefined);
    if (refreshedSet && generationSetRequestRef.current === generationSetRequestId) setActiveGenerationSet(refreshedSet);
    if (focusedJob) {
      initialFocusAppliedRef.current = true;
      setActiveJobId(focusedJob.id);
      setFocusedJobHighlightId(focusedJob.id);
      if (!historyReviewJobId) setHistoryReviewJobId(focusedJob.id);
    }
    return nextJobs;
  };

  const refreshGenerationSet = async (generationGroupId: string) => {
    const requestId = generationSetRequestRef.current + 1;
    generationSetRequestRef.current = requestId;
    const refreshed = await api.generationSet(generationGroupId);
    if (generationSetRequestRef.current !== requestId) return undefined;
    setActiveGenerationSet(refreshed);
    updateGenerationJobs(current => mergeGenerationJobs(current, mapGenerationRetryJobs(refreshed.jobs)));
    return refreshed;
  };

  useEffect(() => {
    let cancelled = false;
    api.generationProviders()
      .then(nextProviders => {
        if (cancelled) return;
        const automatedProviders = nextProviders.filter(nextProvider => nextProvider.provider !== 'manual_upload');
        setProviders(automatedProviders);
        const firstReady = automatedProviders.find(providerCanGenerate) || automatedProviders[0];
        if (firstReady) {
          setProvider(firstReady.provider);
          setOrchestratorModel(firstReady.default_orchestrator_model || firstReady.orchestrator_models?.[0] || 'gpt-5.6-terra');
        }
      })
      .catch(() => {
        if (cancelled) return;
        setProviders([{
          provider: 'openai_codex_oauth_native',
          display_name: 'ChatGPT / Codex OAuth',
          optional: true,
          configured: false,
          authenticated: false,
          available: false,
          state: 'not_configured',
          reason: 'provider_status_unavailable',
          features: { text_to_image: false, text_reference_to_image: false, image_edit: false },
        }]);
      });
    refreshJobs().catch(() => undefined);
    return () => { cancelled = true; jobsRequestRef.current += 1; };
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
    if (batchReviewSession || !initialJobId) return;
    const focused = jobs.find(job => job.id === initialJobId);
    const session = createGenerationReviewSession(jobs, focused);
    if (session) {
      batchReviewCursorJobIdRef.current = focused?.id;
      setBatchReviewSession(session);
    }
  }, [batchReviewSession, initialJobId, jobs]);

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
    if (!batchReviewSession) return;
    const reconciledSession = reconcileGenerationReviewSession(batchReviewSession, jobs);
    if (reconciledSession !== batchReviewSession) {
      setBatchReviewSession(reconciledSession);
      return;
    }
    updateGenerationJobs(current => {
      let changed = false;
      const next = current.map(job => {
        const slot = batchReviewSession.slots.find(candidate => candidate.currentJobId === job.id);
        if (!slot || job.generation_group_id === batchReviewSession.generationGroupId
          && job.generation_group_index === slot.index
          && job.generation_group_size === batchReviewSession.generationGroupSize) return job;
        changed = true;
        return {
          ...job,
          generation_group_id: batchReviewSession.generationGroupId,
          generation_group_index: slot.index,
          generation_group_size: batchReviewSession.generationGroupSize,
        };
      });
      return changed ? next : current;
    });
  }, [batchReviewSession, jobs]);

  useEffect(() => {
    if (!batchReviewSession || batchReviewPaused || historyReviewJobId) return;
    const nextReady = generationReviewNext(jobs, batchReviewSession, batchReviewCursorJobIdRef.current);
    if (!nextReady) return;
    const wasPendingRetry = pendingRetryJobIds.includes(nextReady.id);
    if (wasPendingRetry) setPendingRetryJobIds(current => current.filter(id => id !== nextReady.id));
    batchReviewCursorJobIdRef.current = nextReady.id;
    setActiveJobId(nextReady.id);
    setHistoryReviewJobId(nextReady.id);
    setFocusedJobHighlightId(nextReady.id);
    if (wasPendingRetry) setMessage(t('queueReady'));
  }, [batchReviewPaused, batchReviewSession, historyReviewJobId, jobs, pendingRetryJobIds, t]);

  useEffect(() => {
    setPendingRetryJobIds(current => {
      const retained = retainPendingRetryJobIds(current, jobs);
      return retained.length === current.length && retained.every((jobId, index) => jobId === current[index]) ? current : retained;
    });
  }, [jobs]);

  useEffect(() => {
    if (!providerQueueStates.some(state => providerPauseSeconds(state) > 0)) return undefined;
    setQueueClock(Date.now());
    const timer = window.setInterval(() => setQueueClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [providerQueueStates]);

  useEffect(() => {
    return () => clearGenerationCountCloseTimer();
  }, []);

  useEffect(() => {
    return () => {
      generationSetRequestRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (!isClosing) return undefined;
    return watchMotionEnd(backdropRef.current, () => {
      const pending = pendingAcceptedRef.current;
      pendingAcceptedRef.current = undefined;
      onCloseRef.current();
      if (pending) onAcceptedRef.current(pending.item, pending.message);
    });
  }, [isClosing]);

  useEffect(() => {
    if (!isHistoryDrawerClosing) return undefined;
    return watchMotionEnd(historyDrawerRef.current, () => {
      setShowHistoryDrawer(false);
      setIsHistoryDrawerClosing(false);
      historyTriggerRef.current?.focus({ preventScroll: true });
    });
  }, [isHistoryDrawerClosing]);

  useEffect(() => {
    if (!showHistoryDrawer || isHistoryDrawerClosing) return undefined;
    const frame = window.requestAnimationFrame(() => {
      historyDrawerRef.current?.querySelector<HTMLElement>('button:not([disabled]), [tabindex]:not([tabindex="-1"])')?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [showHistoryDrawer, isHistoryDrawerClosing]);

  useEffect(() => {
    if (!isSavePanelClosing) return undefined;
    return watchMotionEnd(metadataPanelRef.current, () => {
      setReviewJob(undefined);
      setMetadataDraft(undefined);
      setMetadataTagsText('');
      setMetadataTagQuery('');
      setIsSavePanelClosing(false);
      const trigger = saveAsNewTriggerRef.current;
      if (trigger?.isConnected) trigger.focus({ preventScroll: true });
    });
  }, [isSavePanelClosing]);

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

  useEffect(() => {
    if (!referenceMenuOpen) return undefined;
    const frame = window.requestAnimationFrame(() => {
      referenceAddWrapRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus({ preventScroll: true });
    });
    const closeOutside = (event: PointerEvent) => {
      if (!referenceAddWrapRef.current?.contains(event.target as Node)) setReferenceMenuOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('pointerdown', closeOutside);
    };
  }, [referenceMenuOpen]);

  const handleGenerationCountMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(generationCountMenuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') || []);
    if (event.key === 'Escape') {
      if (!generationCountMenuOpen) return;
      event.preventDefault();
      event.stopPropagation();
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
    window.requestAnimationFrame(() => scrollIntoViewRespectingMotion(focusedJobRef.current, 'center'));
    const timer = window.setTimeout(() => setFocusedJobHighlightId(undefined), 4200);
    return () => window.clearTimeout(timer);
  }, [focusedJobHighlightId]);

  useEffect(() => {
    if (!reviewJob || !metadataDraft) return;
    window.requestAnimationFrame(() => {
      scrollIntoViewRespectingMotion(metadataPanelRef.current, 'start');
      metadataPanelRef.current?.focus({ preventScroll: true });
    });
  }, [reviewJob?.id]);

  useEffect(() => {
    const syncFullscreenState = () => setIsStageFullscreen(document.fullscreenElement === fullscreenFrameRef.current);
    document.addEventListener('fullscreenchange', syncFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState);
  }, []);

  useEffect(() => {
    let focusTarget: HTMLElement | null = null;
    if (isStageFullscreen) {
      fullscreenWasOpenRef.current = true;
      focusTarget = fullscreenCloseRef.current;
    } else if (fullscreenWasOpenRef.current) {
      fullscreenWasOpenRef.current = false;
      focusTarget = fullscreenTriggerRef.current;
    }
    if (!focusTarget) return undefined;
    const frame = window.requestAnimationFrame(() => focusTarget?.focus({ preventScroll: true }));
    return () => window.cancelAnimationFrame(frame);
  }, [isStageFullscreen]);

  useEffect(() => {
    if (!selectedStageJob || !['succeeded', 'failed'].includes(selectedStageJob.status)) return;
    window.requestAnimationFrame(() => scrollIntoViewRespectingMotion(stageRef.current, 'start'));
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
    const preservePausedReview = Boolean(batchReviewSession && batchReviewPaused);
    setBusy(true);
    setMessage('');
    setGenerationCountMenuOpen(false);
    setHistoryReviewJobId(undefined);
    jobsRequestRef.current += 1;
    invalidateGenerationSetRequest();
    window.requestAnimationFrame(() => scrollIntoViewRespectingMotion(stageRef.current, 'start'));
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
        setActiveGenerationSetSafely(undefined);
      } else {
        const createdSet = await api.createGenerationSet({ job: jobPayload, count });
        createdJobs = createdSet.jobs;
        setActiveGenerationSetSafely(createdSet);
      }
      invalidateGenerationRefreshRequests();
      updateGenerationJobs(current => mergeGenerationJobs(current, createdJobs));
      if (!preservePausedReview) {
        if (count > 1 && createdJobs[0]) {
          setBatchReviewSession(createGenerationReviewSession(createdJobs, createdJobs[0]));
          setBatchReviewPaused(false);
          setPendingRetryJobIds([]);
        } else {
          setBatchReviewSession(undefined);
          setBatchReviewPaused(false);
          setPendingRetryJobIds([]);
        }
      }
      setActiveJobId(createdJobs[0]?.id);
      onQueueChangedRef.current?.();
    window.requestAnimationFrame(() => scrollIntoViewRespectingMotion(stageRef.current, 'start'));
      setMessage(provider === 'manual_upload'
        ? `${t('queueQueued')}. ${t('uploadImage')}.`
        : count > 1
          ? `${t('generationSet')} ${t('queueQueued').toLowerCase()} · ${count}`
          : `${attachments.length > 0 ? t('useResultAsEditInput') : t('generate')} · ${t('queueQueued').toLowerCase()}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('generationCreateFailed'));
    } finally {
      setBusy(false);
    }
  };

  const cancelRemainingGenerationSet = async () => {
    if (!activeGenerationSet?.remaining || cancelSetBusy) return;
    setCancelSetBusy(true);
    invalidateGenerationSetRequest();
    try {
      const cancelled = await api.cancelRemainingGenerationSet(activeGenerationSet.generation_group_id);
      invalidateGenerationRefreshRequests();
      setActiveGenerationSetSafely(cancelled);
      updateGenerationJobs(current => mergeGenerationJobs(current, cancelled.jobs));
      onQueueChangedRef.current?.();
       setMessage(`${t('cancelRemaining').replace('${remaining}', '0')} · ${t('queueReady')}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('queueCancelSetFailed'));
    } finally {
      setCancelSetBusy(false);
    }
  };

  const runJob = async (job: GenerationJobRecord) => {
    setBusy(true);
    setActiveJobId(job.id);
    setHistoryReviewJobId(undefined);
    setMessage(t('generating'));
    invalidateGenerationRefreshRequests();
    updateGenerationJobs(current => current.map(candidate => candidate.id === job.id ? { ...candidate, status: 'running' } : candidate));
    try {
      const updated = await api.runGenerationJob(job.id);
      invalidateGenerationRefreshRequests();
      updateGenerationJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      onQueueChangedRef.current?.();
      setMessage(updated.status === 'succeeded' ? t('queueReady') : `${t('queueStatus')}: ${statusLabel(updated.status, t)}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('generationRunFailed'));
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const queueAccepted = (acceptedItem?: ItemDetail, message?: string) => {
    pendingAcceptedRef.current = { item: acceptedItem, message };
    handleClose(true);
  };

  const acceptAttach = async (job: GenerationJobRecord) => {
    if (!item) return;
    const reviewSession = ensureBatchReviewSession(job);
    setBusy(true);
    setMessage('');
    try {
      const result = await api.acceptGenerationJob(job.id);
      const acceptedJob = result.job.result_path ? result.job : { ...result.job, result_path: job.result_path };
      invalidateGenerationRefreshRequests();
      const nextJobs = updateGenerationJobs(current => current.map(candidate => candidate.id === acceptedJob.id ? acceptedJob : candidate));
      onQueueChangedRef.current?.();
      setMessage(t('imageAddedToItem'));
      if (reviewSession) {
        const resolvedSession = resolveGenerationReviewSlot(reviewSession, acceptedJob, 'attached', {
          targetItemId: result.item?.id,
          targetItemTitle: result.item?.title,
          resultPath: job.result_path || undefined,
        });
        setBatchReviewSession(resolvedSession);
        onAcceptedRef.current(undefined, t('imageAddedToItem'));
        advanceBatchReview(acceptedJob, resolvedSession, nextJobs);
      } else {
        queueAccepted(result.item, t('imageAddedToItem'));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('generationAcceptFailed'));
    } finally {
      setBusy(false);
    }
  };

  const openSaveAsNewReview = (job: GenerationJobRecord) => {
    ensureBatchReviewSession(job);
    const initialMetadata = buildInitialMetadata(job, item);
    setIsSavePanelClosing(false);
    setReviewJob(job);
    setMetadataDraft(initialMetadata);
    setMetadataTagsText((initialMetadata.tags || []).join(', '));
    setMetadataTagQuery('');
  };

  const closeSaveAsNewReview = () => {
    if (busy || isSavePanelClosing) return;
    setIsSavePanelClosing(true);
  };

  const handleClose = (force = false) => {
    if (busy && !force) return;
    if (isClosing) return;
    setIsClosing(true);
  };

  const closeGenerationControl = (control = openControl) => {
    setOpenControl(null);
    if (control) window.requestAnimationFrame(() => controlTriggerRefs.current[control]?.focus({ preventScroll: true }));
  };

  const closeReferenceMenu = () => {
    setReferenceMenuOpen(false);
    window.requestAnimationFrame(() => referenceAddTriggerRef.current?.focus({ preventScroll: true }));
  };

  const handleReferenceSourceMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(referenceAddWrapRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') || []);
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeReferenceMenu();
      return;
    }
    if (!items.length || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const currentIndex = items.findIndex(item => item === document.activeElement);
    if (event.key === 'Home') items[0].focus();
    else if (event.key === 'End') items[items.length - 1]?.focus();
    else if (event.key === 'ArrowDown') items[(currentIndex + 1 + items.length) % items.length].focus();
    else items[(currentIndex - 1 + items.length) % items.length].focus();
  };

  const closeReferencePicker = () => {
    libraryItemRequestRef.current += 1;
    setReferencePicker(null);
    window.requestAnimationFrame(() => referenceAddTriggerRef.current?.focus({ preventScroll: true }));
  };

  useEffect(() => {
    if (referencePicker !== 'library') return;
    const frame = window.requestAnimationFrame(() => {
      (libraryItem ? libraryItemBackRef.current : librarySearchRef.current)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [libraryItem, referencePicker]);

  const openHistoryDrawer = () => {
    setIsHistoryDrawerClosing(false);
    setShowHistoryDrawer(true);
  };

  const closeHistoryDrawer = () => {
    if (!showHistoryDrawer || isHistoryDrawerClosing) return;
    setIsHistoryDrawerClosing(true);
  };

  const handleHistoryDrawerKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    event.stopPropagation();
    if (event.key === 'Escape') {
      event.preventDefault();
      closeHistoryDrawer();
      return;
    }
    if (event.key !== 'Tab' || !historyDrawerRef.current) return;
    const focusable = Array.from(historyDrawerRef.current.querySelectorAll<HTMLElement>(HISTORY_FOCUSABLE_SELECTOR))
      .filter(element => element.getClientRects().length > 0 || element === document.activeElement);
    if (!focusable.length) {
      event.preventDefault();
      historyDrawerRef.current.focus({ preventScroll: true });
      return;
    }
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

  const selectSibling = (job?: GenerationJobRecord) => {
    if (!job) return;
    setActiveJobId(job.id);
    setFocusedJobHighlightId(job.id);
    if (historyReviewJobId) setHistoryReviewJobId(job.id);
  };

  const openReviewTarget = (targetItemId?: string, targetItemTitle?: string) => {
    if (!targetItemId) return;
    // App's existing onAccepted flow closes Generation first, then opens the
    // Item Detail modal by id (which fetches the full item when needed).
    pendingAcceptedRef.current = {
      item: { id: targetItemId } as ItemDetail,
      message: targetItemTitle ? `${t('viewItem')}: ${targetItemTitle}` : t('viewItem'),
    };
    handleClose(true);
  };

  const handleGenerationDialogKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const target = event.target as HTMLElement | null;
    const editingText = target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || Boolean(target?.isContentEditable)
      || Boolean(target?.closest('[contenteditable="true"]'));
    if (!editingText && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey && siblingNavigation.total > 1) {
      if (event.key === 'ArrowLeft' && siblingNavigation.previous) {
        event.preventDefault();
        selectSibling(siblingNavigation.previous);
        return;
      }
      if (event.key === 'ArrowRight' && siblingNavigation.next) {
        event.preventDefault();
        selectSibling(siblingNavigation.next);
        return;
      }
    }
    handleModalKeyDown(event);
  };

  const handleGenerationEscape = () => {
    if (referencePicker) {
      closeReferencePicker();
      return;
    }
    if (generationCountMenuOpen) {
      setGenerationCountMenuOpen(false);
      generationCountTriggerRef.current?.focus({ preventScroll: true });
      return;
    }
    if (openControl) {
      closeGenerationControl(openControl);
      return;
    }
    if (referenceMenuOpen) {
      closeReferenceMenu();
      return;
    }
    if (showHistoryDrawer) {
      closeHistoryDrawer();
      return;
    }
    if (reviewJob && metadataDraft) {
      closeSaveAsNewReview();
      return;
    }
    if (isStageFullscreen) {
      void closeStageFullscreen();
      return;
    }
    handleClose();
  };
  const generationFallbackSelector = item
    ? '.generate-variant-button, .mobile-generate-variant-button'
    : '.generate-fab';
  const { containerRef: generationDialogRef, handleModalKeyDown } = useModalFocus<HTMLElement>(handleGenerationEscape, {
    fallbackFocusSelector: generationFallbackSelector,
    secondaryFallbackFocusSelector: item ? '.detail.modal' : undefined,
  });
  const { containerRef: saveAsNewDialogRef, handleModalKeyDown: handleSaveAsNewDialogKeyDown } = useModalFocus<HTMLElement>(
    closeSaveAsNewReview,
    { active: Boolean(reviewJob && metadataDraft), fallbackFocusSelector: '.generation-workspace-close' },
  );
  const { containerRef: referencePickerDialogRef, handleModalKeyDown: handleReferencePickerKeyDown } = useModalFocus<HTMLElement>(
    closeReferencePicker,
    { active: Boolean(referencePicker), fallbackFocusSelector: '.generation-reference-add' },
  );

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
    try {
      const loaded = await Promise.all(limitedFiles.map(file => new Promise<EditAttachment>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ id: `upload-${Date.now()}-${file.name}-${Math.random().toString(36).slice(2)}`, name: file.name, source: 'uploaded', previewUrl: String(reader.result), dataUrl: String(reader.result) });
        reader.onerror = () => reject(reader.error || new Error(t('attachmentReadFailed')));
        reader.readAsDataURL(file);
      })));
      setEditAttachments(current => [...current, ...loaded].slice(0, MAX_EDIT_ATTACHMENTS));
      setMessage(loaded.length < nextFiles.length
        ? t('attachmentsAdded').replace('${count}', String(loaded.length)).replace('${limit}', String(MAX_EDIT_ATTACHMENTS))
        : t('attachmentAdded'));
    } catch {
      setMessage(t('attachmentReadFailed'));
    } finally {
      if (attachmentInputRef.current) attachmentInputRef.current.value = '';
    }
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
    const requestId = ++libraryItemRequestRef.current;
    if (libraryItems.length) {
      setPickerBusy(false);
      return;
    }
    setPickerBusy(true);
    try {
      const result = await api.items({ limit: 1000, sort: 'updated_desc' });
      if (requestId === libraryItemRequestRef.current) {
        setLibraryItems(result.items.filter(candidate => candidate.first_image));
      }
    } catch (error) {
      if (requestId === libraryItemRequestRef.current) {
        setMessage(error instanceof Error ? error.message : t('loadFailed'));
        setReferencePicker(null);
      }
    } finally {
      if (requestId === libraryItemRequestRef.current) setPickerBusy(false);
    }
  };

  const openLibraryItem = async (candidate: ItemSummary) => {
    const requestId = ++libraryItemRequestRef.current;
    setPickerBusy(true);
    try {
      const detail = await api.item(candidate.id);
      if (requestId === libraryItemRequestRef.current) setLibraryItem(detail);
    } catch (error) {
      if (requestId === libraryItemRequestRef.current) setMessage(error instanceof Error ? error.message : t('loadFailed'));
    } finally {
      if (requestId === libraryItemRequestRef.current) setPickerBusy(false);
    }
  };

  const openRecentPicker = async () => {
    setReferenceMenuOpen(false);
    setReferencePicker('recent');
    const requestId = ++libraryItemRequestRef.current;
    setPickerBusy(true);
    try {
      const result = await api.generationJobs({ limit: 100 });
      if (requestId === libraryItemRequestRef.current) {
        setRecentJobs(result.jobs.filter(candidate => Boolean(candidate.result_path) && ['succeeded', 'accepted'].includes(candidate.status)));
      }
    } catch (error) {
      if (requestId === libraryItemRequestRef.current) {
        setMessage(error instanceof Error ? error.message : t('loadFailed'));
        setReferencePicker(null);
      }
    } finally {
      if (requestId === libraryItemRequestRef.current) setPickerBusy(false);
    }
  };

  const addResultAsAttachment = (job: GenerationJobRecord, pauseBatchReview = false) => {
    if (!job.result_path || editAttachments.length >= MAX_EDIT_ATTACHMENTS) return;
    const reviewSession = pauseBatchReview ? ensureBatchReviewSession(job) : undefined;
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
    if (reviewSession) setBatchReviewPaused(true);
     setMessage(t('useResultAsEditInput'));
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
    const reviewSession = ensureBatchReviewSession(reviewJob);
    const metadataPayload = {
      ...metadataDraft,
      tags: metadataTagsText.split(',').map(tag => tag.trim()).filter(Boolean),
    } as GenerationJobAcceptAsNewItemPayload;
    setBusy(true);
    setMessage('');
    try {
      const result = await api.acceptGenerationJobAsNewItem(reviewJob.id, metadataPayload);
      const acceptedJob = result.job.result_path ? result.job : { ...result.job, result_path: reviewJob.result_path };
      invalidateGenerationRefreshRequests();
      const nextJobs = updateGenerationJobs(current => current.map(candidate => candidate.id === acceptedJob.id ? acceptedJob : candidate));
      onQueueChangedRef.current?.();
      setReviewJob(undefined);
      setMetadataDraft(undefined);
      setMetadataTagsText('');
      setMetadataTagQuery('');
      setMessage(t('newVariantCreated'));
      if (reviewSession) {
        const resolvedSession = resolveGenerationReviewSlot(reviewSession, acceptedJob, 'saved', {
          targetItemId: result.item?.id,
          targetItemTitle: result.item?.title,
          resultPath: reviewJob.result_path || undefined,
        });
        setBatchReviewSession(resolvedSession);
        onAcceptedRef.current(undefined, t('newVariantCreated'));
        advanceBatchReview(acceptedJob, resolvedSession, nextJobs);
      } else {
        queueAccepted(result.item, t('newVariantCreated'));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  const cancelJob = async (job: GenerationJobRecord) => {
    const reviewSession = ensureBatchReviewSession(job);
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const updated = await api.cancelGenerationJob(job.id);
      invalidateGenerationRefreshRequests();
      const nextJobs = updateGenerationJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      onQueueChangedRef.current?.();
      setMessage(t('queueCancelled'));
      if (reviewSession) {
        const resolvedSession = resolveGenerationReviewSlot(reviewSession, updated, 'cancelled');
        setBatchReviewSession(resolvedSession);
        advanceBatchReview(updated, resolvedSession, nextJobs);
      } else {
        if (historyReviewJobId === updated.id) setHistoryReviewJobId(undefined);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('queueCancelFailed'));
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const discardJob = async (job: GenerationJobRecord) => {
    const reviewSession = ensureBatchReviewSession(job);
    setBusy(true);
    setMessage('');
    try {
      const updated = await api.discardGenerationJob(job.id);
      const discardedJob = { ...updated, result_path: null };
      invalidateGenerationRefreshRequests();
      const nextJobs = updateGenerationJobs(current => current.map(candidate => candidate.id === discardedJob.id ? discardedJob : candidate));
      onQueueChangedRef.current?.();
      setMessage(t('queueDiscarded'));
      if (reviewSession) {
        const resolvedSession = resolveGenerationReviewSlot(reviewSession, discardedJob, 'discarded');
        setBatchReviewSession(resolvedSession);
        advanceBatchReview(discardedJob, resolvedSession, nextJobs);
      } else {
        if (activeJobId === discardedJob.id) setActiveJobId(undefined);
        if (historyReviewJobId === discardedJob.id) setHistoryReviewJobId(undefined);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('queueDiscardFailed'));
    } finally {
      setBusy(false);
    }
  };

  const discardAndRetryJob = async (job: GenerationJobRecord) => {
    const reviewSession = ensureBatchReviewSession(job);
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const result = await api.discardAndRetryGenerationJob(job.id);
      const slotIndex = reviewSession?.slots.find(slot => slot.currentJobId === job.id || slot.originalJobId === job.id)?.index;
      const retryJob = reviewSession && slotIndex ? {
        ...result.retry_job,
        generation_group_id: reviewSession.generationGroupId,
        generation_group_index: slotIndex,
        generation_group_size: reviewSession.generationGroupSize,
      } : result.retry_job;
      invalidateGenerationRefreshRequests();
      const nextJobs = updateGenerationJobs(current => [
        retryJob,
        ...current
          .map(candidate => candidate.id === result.discarded_job.id ? result.discarded_job : candidate)
          .filter(candidate => candidate.id !== retryJob.id),
      ]);
      setPromptText(jobPrompt(retryJob));
      setAspectRatio(jobAspectRatio(retryJob));
      setQuality(jobQuality(retryJob));
      setProvider(retryJob.provider || provider);
      setOrchestratorModel(jobModel(retryJob));
      setEditAttachments(restorableJobAttachments(retryJob));
      setFocusedJobHighlightId(retryJob.id);
      onQueueChangedRef.current?.();
      if (reviewSession) {
        const mappedSession = mapGenerationRetryToReviewSlot(reviewSession, job, retryJob);
        setBatchReviewSession(mappedSession);
        setPendingRetryJobIds(current => [...new Set([...current, retryJob.id])]);
        advanceBatchReview(retryJob, mappedSession, nextJobs);
      } else {
        setActiveJobId(retryJob.id);
        setHistoryReviewJobId(undefined);
      }
      setMessage(t('queueRetry'));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('queueRetryFailedError'));
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const retryFailedJob = async (job: GenerationJobRecord) => {
    const reviewSession = ensureBatchReviewSession(job);
    if (!canRetryFailedJob(job)) {
      const retryId = retriedByJobId(job);
      if (retryId) {
        let retryJob = jobsRef.current.find(candidate => candidate.id === retryId);
        if (!retryJob) {
          setBusy(true);
          setMessage('');
          try {
            const fetchedRetryJob = await api.generationJob(retryId);
            const slotIndex = reviewSession?.slots.find(slot => slot.currentJobId === job.id || slot.originalJobId === job.id)?.index;
            retryJob = reviewSession && slotIndex ? {
              ...fetchedRetryJob,
              generation_group_id: reviewSession.generationGroupId,
              generation_group_index: slotIndex,
              generation_group_size: reviewSession.generationGroupSize,
            } : fetchedRetryJob;
            invalidateGenerationRefreshRequests();
            updateGenerationJobs(current => mergeGenerationJobs(current, [retryJob as GenerationJobRecord]));
          } catch (error) {
            setMessage(error instanceof Error ? error.message : t('queueRetryFailedError'));
            return;
          } finally {
            setBusy(false);
          }
        }
        if (reviewSession && retryJob) {
          const mappedSession = mapGenerationRetryToReviewSlot(reviewSession, job, retryJob);
          setBatchReviewSession(mappedSession);
          setPendingRetryJobIds(current => [...new Set([...current, retryJob.id])]);
          advanceBatchReview(retryJob, mappedSession, jobsRef.current);
        } else {
          setActiveJobId(retryId);
          setHistoryReviewJobId(undefined);
          setFocusedJobHighlightId(retryId);
        }
      }
      return;
    }
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const retry = await api.retryGenerationJob(job.id);
      const slotIndex = reviewSession?.slots.find(slot => slot.currentJobId === job.id || slot.originalJobId === job.id)?.index;
      const retryJob = reviewSession && slotIndex ? {
        ...retry,
        generation_group_id: reviewSession.generationGroupId,
        generation_group_index: slotIndex,
        generation_group_size: reviewSession.generationGroupSize,
      } : retry;
      invalidateGenerationRefreshRequests();
      const nextJobs = updateGenerationJobs(current => [retryJob, ...current.filter(candidate => candidate.id !== retryJob.id)]);
      setPromptText(jobPrompt(retry));
      setAspectRatio(jobAspectRatio(retry));
      setQuality(jobQuality(retry));
      setProvider(retryJob.provider || provider);
      setOrchestratorModel(jobModel(retryJob));
      setEditAttachments(restorableJobAttachments(retryJob));
      setFocusedJobHighlightId(retryJob.id);
      onQueueChangedRef.current?.();
      if (reviewSession) {
        const mappedSession = mapGenerationRetryToReviewSlot(reviewSession, job, retryJob);
        setBatchReviewSession(mappedSession);
        setPendingRetryJobIds(current => [...new Set([...current, retryJob.id])]);
        advanceBatchReview(retryJob, mappedSession, nextJobs);
      } else {
        setActiveJobId(retryJob.id);
        setHistoryReviewJobId(undefined);
      }
      setMessage(t('queueRetried'));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('queueRetryFailedError'));
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const markStaleRunningJobFailed = async (job: GenerationJobRecord) => {
    if (!isStaleRunningJob(job)) return;
    const reviewSession = ensureBatchReviewSession(job);
    setBusy(true);
    setActiveJobId(job.id);
    setMessage('');
    try {
      const updated = await api.markGenerationJobFailed(job.id);
      invalidateGenerationRefreshRequests();
      updateGenerationJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      const nextSession = reviewSession ? resolveGenerationReviewSlot(reviewSession, updated, 'failed') : undefined;
      if (nextSession) setBatchReviewSession(nextSession);
      if (reviewSession) advanceBatchReview(updated, nextSession, jobsRef.current);
      else setHistoryReviewJobId(undefined);
      onQueueChangedRef.current?.();
       setMessage(t('markFailed'));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t('queueMarkFailedError'));
      await refreshJobs().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const previewHistoryJob = (job: GenerationJobRecord) => {
    ensureBatchReviewSession(job);
    setHistoryReviewJobId(job.id);
    setActiveJobId(job.id);
    closeHistoryDrawer();
  };

  const useJobAsDraft = (job: GenerationJobRecord) => {
    const reviewSession = ensureBatchReviewSession(job);
    const attachments = jobAttachments(job);
    const restorableAttachments = restorableJobAttachments(job);
    setPromptText(jobPrompt(job));
    setAspectRatio(jobAspectRatio(job));
    setQuality(jobQuality(job));
    setProvider(job.provider || provider);
    setOrchestratorModel(jobModel(job));
    setEditAttachments(restorableAttachments);
    setHistoryReviewJobId(undefined);
    if (reviewSession) setBatchReviewPaused(true);
    setMessage(attachments.length > restorableAttachments.length ? `${t('copyPrompt')}. ${t('uploadImage')}.` : `${t('copyPrompt')}.`);
    window.requestAnimationFrame(() => {
      scrollIntoViewRespectingMotion(promptInputRef.current, 'center');
      promptInputRef.current?.focus({ preventScroll: true });
    });
  };

  const copyJobPrompt = async (job: GenerationJobRecord) => {
    const text = jobPrompt(job);
    try {
      await navigator.clipboard?.writeText(text);
      setMessage(`${t('copyPrompt')}.`);
    } catch {
      setMessage(text ? `${t('copyPrompt')}.` : t('noGenerationJobs'));
    }
  };

  const renderReferenceTray = (attachments: EditAttachment[], readOnly = false) => {
    if (readOnly && attachments.length === 0) return null;
    return (
    <div className={`generation-reference-tray${readOnly ? ' is-readonly' : ''}`} aria-label={readOnly ? t('generationReferencesUsed') : t('generationReferences')}>
      <div className="generation-reference-tray-head">
        <strong>{readOnly ? t('generationReferencesUsed') : t('generationReferences')}</strong>
        <span>{attachments.length} / {MAX_EDIT_ATTACHMENTS}</span>
      </div>
      <div className="generation-reference-row">
        <div className="generation-reference-items">
          {attachments.map((attachment, index) => (
          <div className="generation-reference-card" key={attachment.id} title={attachment.name}>
            <span className="generation-reference-number">{index + 1}</span>
            {attachment.previewUrl ? <img src={attachment.previewUrl} alt="" loading="lazy" /> : <span className="generation-reference-placeholder"><Images size={15} /></span>}
            <span className="generation-reference-copy">
              <b>{attachment.source === 'library' ? t('generationLibrary') : attachment.source === 'generated_result' ? t('generationGenerated') : t('generationUpload')}</b>
              <em>{attachment.name}</em>
            </span>
            {!readOnly && (
              <span className="generation-reference-actions">
                <button type="button" onClick={() => moveAttachment(index, -1)} disabled={index === 0} aria-label={`${t('moveReferenceLeft')}: ${attachment.name}`}><ChevronLeft size={13} /></button>
                <button type="button" onClick={() => moveAttachment(index, 1)} disabled={index === attachments.length - 1} aria-label={`${t('moveReferenceRight')}: ${attachment.name}`}><ChevronRight size={13} /></button>
                <button type="button" onClick={() => removeAttachment(attachment.id)} aria-label={`${t('removeReference')}: ${attachment.name}`}><X size={13} /></button>
              </span>
            )}
          </div>
          ))}
        </div>
        {!readOnly && attachments.length < MAX_EDIT_ATTACHMENTS && (
          <div ref={referenceAddWrapRef} className="generation-reference-add-wrap">
            <button ref={referenceAddTriggerRef} type="button" className="generation-reference-add" onClick={() => setReferenceMenuOpen(current => !current)} aria-label={t('addGenerationReference')} aria-haspopup="menu" aria-expanded={referenceMenuOpen}><Plus size={16} /> {t('add')}</button>
            {referenceMenuOpen && (
              <div className="generation-reference-source-menu" role="menu" onKeyDown={handleReferenceSourceMenuKeyDown}>
                <button type="button" role="menuitem" onClick={() => { closeReferenceMenu(); attachmentInputRef.current?.click(); }}><Upload size={15} /> {t('uploadImage')}</button>
                <button type="button" role="menuitem" onClick={() => openLibraryPicker().catch(() => undefined)}><Images size={15} /> {t('chooseFromLibrary')}</button>
                <button type="button" role="menuitem" onClick={() => openRecentPicker().catch(() => undefined)}><Clock3 size={15} /> {t('chooseRecentResult')}</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
    );
  };

  const renderStageActions = (job: GenerationJobRecord) => (
    <div className="generation-stage-actions" aria-label={t('resultActions')}>
      {canAttachToSourceItem(job) && (
        <button className="stage-action" onClick={() => acceptAttach(job)} disabled={busy} aria-label={t('attachToCurrentItem')} title={t('attachToCurrentItem')}>
          <Paperclip size={16} aria-hidden="true" />
        </button>
      )}
      <button ref={saveAsNewTriggerRef} className="stage-action" onClick={() => openSaveAsNewReview(job)} disabled={busy} aria-label={t('saveAsNewItem')} title={t('saveAsNewItem')}>
        <FilePlus2 size={16} aria-hidden="true" />
      </button>
      <button className="stage-action" onClick={() => addResultAsAttachment(job, true)} disabled={busy || editAttachments.length >= MAX_EDIT_ATTACHMENTS || !job.result_path} aria-label={t('useResultAsEditInput')} title={t('useResultAsEditInput')}>
        <Plus size={16} aria-hidden="true" />
      </button>
      <button className="stage-action" onClick={() => discardAndRetryJob(job)} disabled={busy} aria-label={t('retry')} title={t('retry')}>
        <RotateCcw size={16} aria-hidden="true" />
      </button>
      {canDiscardTransientResult(job) && (
        <button className="stage-action danger" onClick={() => discardJob(job)} disabled={busy} aria-label={t('discard')} title={t('discard')}>
          <Trash2 size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );

  const renderSiblingNavigation = () => {
    const stableSlot = batchReviewSession && selectedStageJob?.generation_group_id === batchReviewSession.generationGroupId
      ? batchReviewSession.slots.find(slot => slot.currentJobId === selectedStageJob.id || slot.originalJobId === selectedStageJob.id)
      : undefined;
    const stableNavigation = batchReviewSession && stableSlot
      ? generationReviewSlotNavigation(batchReviewSession, selectedStageJob?.id)
      : undefined;
    const previousReviewJob = stableNavigation?.previous && jobs.find(job => job.id === stableNavigation.previous?.currentJobId || job.id === stableNavigation.previous?.originalJobId);
    const nextReviewJob = stableNavigation?.next && jobs.find(job => job.id === stableNavigation.next?.currentJobId || job.id === stableNavigation.next?.originalJobId);
    if (!stableSlot && siblingNavigation.total < 2) return null;
    const position = stableSlot ? `${stableSlot.index} / ${batchReviewSession?.generationGroupSize}` : `${siblingNavigation.index + 1} / ${siblingNavigation.total}`;
    const previousJob = stableSlot ? previousReviewJob : siblingNavigation.previous;
    const nextJob = stableSlot ? nextReviewJob : siblingNavigation.next;
    return (
      <div className="generation-sibling-navigation" role="group" aria-label={t('generationBatchNavigation')}>
        <button className="generation-sibling-previous" type="button" onClick={() => selectSibling(previousJob)} disabled={!previousJob} aria-label={t('generationPrevious')} title={t('generationPrevious')}>
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <span className="generation-sibling-count" aria-live="polite">{position}</span>
        <button className="generation-sibling-next" type="button" onClick={() => selectSibling(nextJob)} disabled={!nextJob} aria-label={t('generationNext')} title={t('generationNext')}>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    );
  };

  const resumeBatchReview = () => {
    if (!batchReviewSession) return;
    const nextJob = generationReviewNext(jobsRef.current, batchReviewSession, batchReviewCursorJobIdRef.current);
    setBatchReviewPaused(false);
    if (nextJob) {
      batchReviewCursorJobIdRef.current = nextJob.id;
      setActiveJobId(nextJob.id);
      setHistoryReviewJobId(nextJob.id);
      setFocusedJobHighlightId(nextJob.id);
      return;
    }
    setMessage(t('generationReady'));
  };

  const renderBatchReviewSummary = () => {
    if (!batchReviewActive || !batchReviewSummary || batchReviewSummary.actionable > 0) return null;
    const items = [
      [t('reviewSaved'), batchReviewSummary.saved],
      [t('reviewAttached'), batchReviewSummary.attached],
      [t('reviewDiscarded'), batchReviewSummary.discarded],
      [t('reviewRetrying'), batchReviewSummary.pendingRetry],
      [t('reviewGenerating'), batchReviewSummary.pendingGeneration],
      [t('reviewFailedOrCancelled'), batchReviewSummary.failedOrCancelled],
    ].filter(([, count]) => Number(count) > 0) as [string, number][];
    return (
      <section className={`generation-batch-review-summary${batchReviewSummary.complete ? ' is-complete' : ' is-pending'}`} aria-live="polite">
        <strong>{batchReviewSummary.complete ? t('reviewComplete') : t('generationSet')}</strong>
        <span className="generation-batch-review-counts">
          {items.map(([label, count]) => <span key={label}><b>{count}</b> {label}</span>)}
        </span>
      </section>
    );
  };

  const renderBatchReviewResume = () => {
    if (!batchReviewPaused || !batchReviewSession || !batchReviewSummary) return null;
    const remaining = batchReviewSummary.actionable + batchReviewSummary.pendingRetry + batchReviewSummary.pendingGeneration;
    return <div className="generation-review-resume"><button type="button" className="secondary" onClick={resumeBatchReview}>{t('continueReview').replace('${count}', String(remaining))}</button></div>;
  };

  const renderStage = () => {
    if (!selectedStageJob) {
      return <div className="generation-stage generation-stage-ready"><strong>{t('generationReady')}</strong></div>;
    }
    const reviewSlot = batchReviewSession?.slots.find(slot => slot.currentJobId === selectedStageJob.id || slot.originalJobId === selectedStageJob.id);
    const reviewOutcome = reviewSlot?.resolution
      || (pendingRetryJobIds.includes(selectedStageJob.id) ? 'retrying' : undefined)
      || (selectedStageJob.status === 'accepted' ? 'saved' : selectedStageJob.status === 'cancelled' ? 'cancelled' : selectedStageJob.status === 'failed' ? 'failed' : undefined);
    const outcomeLabel = reviewOutcome === 'saved'
      ? t('reviewSaved')
      : reviewOutcome === 'attached'
        ? t('reviewAttached')
        : reviewOutcome === 'discarded'
          ? t('reviewDiscarded')
          : reviewOutcome === 'retrying'
            ? t('reviewRetrying')
            : reviewOutcome === 'failed' || reviewOutcome === 'cancelled'
              ? t('reviewFailedOrCancelled')
              : undefined;
    const reviewTargetId = reviewSlot?.targetItemId;
    const reviewTargetTitle = reviewSlot?.targetItemTitle;
    if (selectedStageJob.status === 'queued' || selectedStageJob.status === 'running') {
      return (
        <div className="generation-stage generation-stage-generating">
          <div className="generation-generating-block generation-shimmer stage-shimmer" />
          <strong>{pendingRetryJobIds.includes(selectedStageJob.id) ? t('reviewRetrying') : t('generating')}</strong>
          <div className="generation-stage-actions generation-cancel-actions" aria-label={t('cancel')}>
            <p className="generation-cancel-note">
              {selectedStageJob.status === 'queued' ? t('queueQueuedCancelNote') : t('queueRunningCancelNote')}
            </p>
            <button className="stage-action danger" type="button" onClick={() => cancelJob(selectedStageJob)} disabled={busy} aria-label={t('cancel')}>
              {t('cancel')}
            </button>
          </div>
          {isStaleRunningJob(selectedStageJob) && (
            <div className="generation-stage-actions" aria-label={t('failedGenerationActions')}>
              <p className="generation-stale-copy">{t('generationStalled')}</p>
              <button className="stage-action" onClick={() => markStaleRunningJobFailed(selectedStageJob)} disabled={busy} aria-label={t('markFailedToRetry')} title={t('markFailedToRetry')}>
                {t('markFailed')}
              </button>
            </div>
          )}
        </div>
      );
    }
    if (selectedStageJob.status === 'failed') {
      const retryId = retriedByJobId(selectedStageJob);
       const failure = generationFailure(selectedStageJob, t);
      const retryButton = canRetryFailedJob(selectedStageJob) ? (
        <button className={`stage-action${failure.kind === 'policy_violation' || failure.kind === 'auth_required' ? '' : ' primary'}`} onClick={() => retryFailedJob(selectedStageJob)} disabled={busy}>
          {t('retry')}
        </button>
      ) : null;
      const editPromptButton = (
        <button className={`stage-action${failure.kind === 'policy_violation' ? ' primary' : ''}`} onClick={() => useJobAsDraft(selectedStageJob)} disabled={busy}>
          {t('editPrompt')}
        </button>
      );
      return (
        <div className="generation-stage generation-stage-error">
          <div className="generation-failure-content">
            <div className="generation-failure-announcement" role="alert">
              <strong>{retryId ? t('retried') : failure.title}</strong>
              <p>{failure.guidance}</p>
              {message && <p className="provider-message generation-failure-message">{message}</p>}
            </div>
            {selectedStageJob.error && (
              <details className="generation-failure-details">
                <summary>{t('providerDetails')}</summary>
                <small>{selectedStageJob.error}</small>
              </details>
            )}
          </div>
          <div className="generation-stage-actions generation-failure-actions" aria-label={t('failedGenerationActions')}>
            {retryId ? (
              <button className="stage-action primary" onClick={() => retryFailedJob(selectedStageJob)} disabled={busy}>
                {t('openRetryJob')}
              </button>
            ) : (
              <>
                {failure.kind === 'policy_violation' && editPromptButton}
                {failure.kind === 'auth_required' && (
                  <button className="stage-action primary" onClick={onOpenProviders} disabled={busy}>
                    {t('openProviders')}
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
    if (reviewOutcome === 'discarded' || selectedStageJob.status === 'discarded') {
      return (
        <div className="generation-stage generation-stage-outcome status-discarded">
          <div className="generation-stage-deleted-placeholder" role="status"><strong>{t('reviewDiscarded')}</strong></div>
          {renderSiblingNavigation()}
        </div>
      );
    }
    const resultUrl = jobResultUrl(selectedStageJob);
    if (resultUrl) {
      return (
        <div className={`generation-stage generation-stage-result${isStageFullscreen ? ' is-mobile-fullscreen' : ''}`}>
          <div ref={fullscreenFrameRef} className="generation-fullscreen-frame">
            <img ref={resultImageRef} className="generation-result-image generation-result-fade-in" src={resultUrl} alt={t('saveGeneratedResultPreview')} />
            {renderSiblingNavigation()}
            {batchReviewSession && outcomeLabel && <span className="generation-stage-outcome-label" role="status">{outcomeLabel}</span>}
            {batchReviewSession && reviewTargetId && (reviewOutcome === 'saved' || reviewOutcome === 'attached') && (
              <button type="button" className="generation-stage-open-target" onClick={() => openReviewTarget(reviewTargetId, reviewTargetTitle)}>{t('viewItem')}</button>
            )}
            <button ref={fullscreenCloseRef} className="modal-icon-button generation-fullscreen-close" type="button" onClick={closeStageFullscreen} aria-label={t('closeFullscreen')}><X size={20} strokeWidth={2.25} /></button>
          </div>
          {canUseResultActions(selectedStageJob) && renderStageActions(selectedStageJob)}
        </div>
      );
    }
    if (selectedStageJob.status === 'accepted') {
      return <div className="generation-stage generation-stage-outcome status-accepted"><strong>{outcomeLabel || t('queueSaved')}</strong>{reviewTargetId && <button type="button" className="secondary" onClick={() => openReviewTarget(reviewTargetId, reviewTargetTitle)}>{t('viewItem')}</button>}{renderSiblingNavigation()}</div>;
    }
    if (selectedStageJob.status === 'cancelled') {
      return <div className="generation-stage generation-stage-outcome status-cancelled"><strong>{t('reviewFailedOrCancelled')}</strong></div>;
    }
    return (
      <div className="generation-stage generation-stage-ready">
        <strong>{statusLabel(selectedStageJob.status, t, isUsedAsGenerationReference(selectedStageJob))}</strong>
        {renderStageActions(selectedStageJob)}
      </div>
    );
  };

  return (
    <div ref={backdropRef} className={`modal-backdrop${isClosing ? ' is-closing' : ''}`} onClick={() => handleClose()}>
      <section
        ref={generationDialogRef}
        className="generation-panel modal polished-modal"
        onClick={event => event.stopPropagation()}
        onKeyDown={handleGenerationDialogKeyDown}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="generation-workspace-title"
      >
        <header className="generation-workspace-head" inert={showHistoryDrawer} aria-hidden={showHistoryDrawer || undefined}>
          <div>
            <p className="modal-kicker">{t('generate')}</p>
            <h2 id="generation-workspace-title">{reviewJob ? t('saveGeneratedImageAsNew') : isHistoryReview ? t('reviewGeneration') : t('createImage')}</h2>
          </div>
          <button className="modal-icon-button generation-workspace-close" onClick={reviewJob ? closeSaveAsNewReview : () => handleClose()} disabled={busy || isClosing || isSavePanelClosing} aria-label={t('close')}>
            <X size={20} strokeWidth={2.25} />
          </button>
        </header>
        {!reviewJob || !metadataDraft ? <div className="generation-layout" inert={showHistoryDrawer} aria-hidden={showHistoryDrawer || undefined}>
          <section className="generation-compose-card generation-composer-card">
            {!isHistoryReview ? (
              <>
                <div className="generation-prompt-area">
                      <textarea ref={promptInputRef} data-modal-initial-focus value={promptText} onChange={event => setPromptText(event.currentTarget.value)} placeholder={t('promptPlaceholder')} aria-label={t('generationPrompt')} />
                  {renderReferenceTray(editAttachments)}
                </div>
                {renderBatchReviewResume()}
                {renderBatchReviewSummary()}
                {hasTemplateVariables && (
                    <div className="generation-template-variable-fields" aria-label={t('promptVariables')}>
                    <div className="generation-template-head">
                      <span>{t('promptVariables')}</span>
                      <em>{t('fillBeforeGenerating')}</em>
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
                            placeholder={`${t('title')}: ${variable.key}`}
                          />
                        </label>
                      ))}
                    </div>
                    <div className="generation-template-preview">
                       <span>{t('finalPrompt')}</span>
                       <p>{resolvedPrompt || t('completeVariables')}</p>
                    </div>
                  </div>
                )}
                <div className={`generation-compact-controls${selectedProviderCanGenerate ? '' : ' has-provider-attention'}`}>
                  <div className="generation-control-wrap">
                     <button ref={element => { controlTriggerRefs.current.aspect = element; }} className="generation-control-trigger generation-aspect-trigger" type="button" onClick={() => setOpenControl(openControl === 'aspect' ? null : 'aspect')} aria-label={`${t('queueAspectRatio')}: ${optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio, t)}`} title={`${t('queueAspectRatio')}: ${optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio, t)}`}>
                      <img className="generation-control-icon" src={aspectRatioIcon} alt="" aria-hidden="true" />
                      <span className="generation-control-value">{optionLabel(ASPECT_RATIO_OPTIONS, aspectRatio, t)}</span>
                    </button>
                    {openControl === 'aspect' && (
                      <div className="generation-control-popover" role="menu">
                        {ASPECT_RATIO_OPTIONS.map(option => (
                           <button key={option.value} type="button" className={aspectRatio === option.value ? 'is-selected' : ''} onClick={() => { setAspectRatio(option.value); closeGenerationControl('aspect'); }}>{optionLabel(ASPECT_RATIO_OPTIONS, option.value, t)}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="generation-control-wrap">
                     <button ref={element => { controlTriggerRefs.current.quality = element; }} className="generation-control-trigger generation-quality-trigger" type="button" onClick={() => setOpenControl(openControl === 'quality' ? null : 'quality')} aria-label={`${t('queueQuality')}: ${optionLabel(QUALITY_OPTIONS, quality, t)}`} title={`${t('queueQuality')}: ${optionLabel(QUALITY_OPTIONS, quality, t)}`}>
                      <img className="generation-control-icon" src={qualityIcon} alt="" aria-hidden="true" />
                      <span className="generation-control-value">{optionLabel(QUALITY_OPTIONS, quality, t)}</span>
                    </button>
                    {openControl === 'quality' && (
                      <div className="generation-control-popover" role="menu">
                        {QUALITY_OPTIONS.map(option => (
                           <button key={option.value} type="button" className={quality === option.value ? 'is-selected' : ''} onClick={() => { setQuality(option.value); closeGenerationControl('quality'); }}>{optionLabel(QUALITY_OPTIONS, option.value, t)}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="generation-control-wrap generation-model-control">
                     <button ref={element => { controlTriggerRefs.current.model = element; }} className="generation-control-trigger generation-model-trigger generation-has-long-value" type="button" onClick={() => setOpenControl(openControl === 'model' ? null : 'model')} disabled={provider !== 'openai_codex_oauth_native'} aria-label={`${t('queueModel')}: ${orchestratorModelLabel(orchestratorModel)}`} title={orchestratorModelLabel(orchestratorModel)}>
                      <img className="generation-control-icon" src={brainAiIcon} alt="" aria-hidden="true" />
                      <span className="generation-control-value">{orchestratorModelLabel(orchestratorModel)}</span>
                    </button>
                    {openControl === 'model' && (
                      <div className="generation-control-popover" role="menu">
                        {orchestratorModels.map(model => (
                          <button key={model} type="button" className={orchestratorModel === model ? 'is-selected' : ''} onClick={() => { setOrchestratorModel(model); closeGenerationControl('model'); }}>{orchestratorModelLabel(model)}</button>
                        ))}
                      </div>
                    )}
                  </div>
                  <input ref={attachmentInputRef} className="generation-attachment-input" type="file" accept="image/*" multiple onChange={event => addUploadedAttachments(event.currentTarget.files)} />
                  <div className="generation-provider-status">
                    <span className={`generation-provider-readiness ${selectedProviderCanGenerate ? 'is-ready' : 'needs-attention'}`} title={selectedProviderMessage} aria-label={selectedProviderMessage}>
                      {compactProviderMessage}
                    </span>
                    {!selectedProviderCanGenerate && (
                      <button type="button" className="generation-provider-connect" onClick={onOpenProviders}>
                        {t('openProviders')}
                      </button>
                    )}
                  </div>
                  <div
                    ref={generationCountMenuRef}
                    className="generation-generate-split"
                     onMouseEnter={() => {
                       clearGenerationCountCloseTimer();
                       generationCountFocusOnOpenRef.current = false;
                       if (window.matchMedia('(hover: hover)').matches) setGenerationCountMenuOpen(true);
                     }}
                     onMouseLeave={scheduleGenerationCountClose}
                    onKeyDown={handleGenerationCountMenuKeyDown}
                    onBlur={event => {
                       if (!event.currentTarget.contains(event.relatedTarget as Node | null)) scheduleGenerationCountClose();
                    }}
                  >
                    <button
                      className="primary generation-primary-action"
                      type="button"
                      onClick={() => createJob(1)}
                      disabled={busy || !selectedProviderCanGenerate || !promptText.trim() || hasMissingTemplateValues}
                       aria-label={`${t('generate')} 1`}
                     >{t('generate')}</button>
                    <button
                        ref={generationCountTriggerRef}
                        className="primary generation-count-trigger"
                        type="button"
                         aria-label={t('chooseGenerationCount')}
                        aria-haspopup="menu"
                        aria-expanded={generationCountMenuOpen}
                        aria-controls="generation-count-menu"
                        onClick={() => {
                          clearGenerationCountCloseTimer();
                          if (generationCountMenuOpen) {
                            generationCountFocusOnOpenRef.current = false;
                            window.requestAnimationFrame(() => generationCountMenuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus());
                            return;
                          }
                          generationCountFocusOnOpenRef.current = true;
                          setGenerationCountMenuOpen(true);
                        }}
                        onKeyDown={event => {
                          if (!['ArrowDown', 'Enter', ' '].includes(event.key)) return;
                          event.preventDefault();
                          generationCountFocusOnOpenRef.current = true;
                          setGenerationCountMenuOpen(true);
                        }}
                        disabled={busy || !selectedProviderCanGenerate || !promptText.trim() || hasMissingTemplateValues}
                      ><ChevronDown size={17} aria-hidden="true" /></button>
                    {generationCountMenuOpen && (
                       <div id="generation-count-menu" className="generation-count-menu" role="menu" aria-label={t('generateVariations')}>
                        {GENERATION_SET_OPTIONS.map(count => (
                          <button key={count} type="button" role="menuitem" onClick={() => createJob(count)}>
                             <strong>{t('generate')} ×{count}</strong>
                             <small>{t('usesGenerations').replace('${count}', String(count))}</small>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                    <button ref={historyTriggerRef} className="generation-history-control" onClick={openHistoryDrawer} aria-label={t('history')} title={t('history')} type="button"><Clock3 size={17} /></button>
                </div>
                {selectedProviderQueueState && selectedProviderPauseSeconds > 0 && (
                   <section className="generation-provider-pause" aria-label={`${t('generationQueuePaused')}: ${selectedProviderQueueState.paused_until || ''}`}>
                     <strong>{t('generationQueuePaused')}</strong>
                     <span aria-hidden="true">{t('rateLimitedResumes').replace('${seconds}', String(selectedProviderPauseSeconds))}</span>
                     {selectedProviderQueueState.paused_until && <time className="sr-only" dateTime={selectedProviderQueueState.paused_until}>{t('pausedUntil').replace('${time}', selectedProviderQueueState.paused_until)}</time>}
                  </section>
                )}
                {activeGenerationSet && (
                  <section className="generation-set-progress" aria-live="polite">
                    <div className="generation-set-progress-head">
                       <strong>{t('generationSet')}</strong>
                       <span>{t('finished').replace('${completed}', String(activeGenerationSet.completed)).replace('${total}', String(activeGenerationSet.total))}</span>
                    </div>
                     <progress max={activeGenerationSet.total} value={activeGenerationSet.completed} aria-label={t('finished').replace('${completed}', String(activeGenerationSet.completed)).replace('${total}', String(activeGenerationSet.total))} />
                     <p>{localizedGenerationSetProgressText(activeGenerationSet, t)}</p>
                    {activeGenerationSet.remaining > 0 && (
                      <button type="button" className="generation-cancel-remaining" onClick={cancelRemainingGenerationSet} disabled={cancelSetBusy}>
                        {t('cancelRemaining').replace('${remaining}', String(activeGenerationSet.remaining))}
                      </button>
                    )}
                  </section>
                )}
              </>
            ) : historyReviewJob && (
              <div className={`generation-history-prompt-preview${jobAttachments(historyReviewJob).length ? ' has-references' : ''}`}>
                 <textarea readOnly value={jobPrompt(historyReviewJob)} aria-label={t('selectedHistoryPrompt')} />
                {renderReferenceTray(jobAttachments(historyReviewJob), true)}
                <div className="generation-history-prompt-actions">
                   <button className="secondary generation-history-back" onClick={() => setHistoryReviewJobId(undefined)}><ArrowLeft size={15} /> {t('backToDraft')}</button>
                   <span className="generation-history-prompt-primary-actions">
                     <button className="secondary" onClick={() => copyJobPrompt(historyReviewJob)}><Clipboard size={15} /> {t('copyPrompt')}</button>
                     <button className="primary" onClick={() => useJobAsDraft(historyReviewJob)}>{t('useAsDraft')}</button>
                   </span>
                </div>
              </div>
            )}
          </section>

          <section ref={stageRef} className="generation-stage-card">
             {selectedStageJob?.result_path && !['discarded', 'cancelled', 'failed'].includes(selectedStageJob.status) && <a className="modal-icon-button generation-download-overlay" href={jobResultUrl(selectedStageJob)} download={downloadFileName('generation-result', selectedStageJob.result_path)} aria-label={t('download')} title={t('download')}><Download size={16} /></a>}
             <button ref={fullscreenTriggerRef} className="modal-icon-button generation-fullscreen-overlay" onClick={toggleStageFullscreen} aria-label={t('viewFullscreen')} title={t('viewFullscreen')}><Maximize2 size={16} /></button>
             {(!selectedStageJob || !jobResultUrl(selectedStageJob)) && renderSiblingNavigation()}
            {renderStage()}
          </section>
        </div> : null}

        {referencePicker && createPortal((
          <div className="generation-reference-picker-backdrop" onClick={closeReferencePicker} onKeyDown={event => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            closeReferencePicker();
          }}>
            <section ref={referencePickerDialogRef} className="generation-reference-picker" role="dialog" aria-modal="true" aria-label={referencePicker === 'library' ? t('chooseImagesFromLibrary') : t('chooseRecentGenerationResult')} onClick={event => event.stopPropagation()} onKeyDown={handleReferencePickerKeyDown} tabIndex={-1}>
              <div className="drawer-head">
                <div>
                <p className="drawer-eyebrow">{t('generationReferences')} · {editAttachments.length} / {MAX_EDIT_ATTACHMENTS}</p>
                <h3>{referencePicker === 'library' ? t('chooseFromLibrary') : t('chooseRecentResult')}</h3>
                </div>
                <button className="modal-icon-button" type="button" onClick={closeReferencePicker} aria-label={t('closeReferencePicker')}><X size={20} /></button>
              </div>
              {pickerBusy && <p className="muted" role="status">{t('loading')}</p>}
              {referencePicker === 'library' && !libraryItem && (
                <>
                   <input ref={librarySearchRef} data-modal-initial-focus className="generation-reference-search" value={libraryQuery} onChange={event => setLibraryQuery(event.currentTarget.value)} placeholder={t('searchLibraryReferences')} aria-label={t('searchLibraryReferences')} />
                  <div className="generation-reference-picker-grid">
                    {libraryItems.filter(candidate => candidate.title.toLowerCase().includes(libraryQuery.trim().toLowerCase())).map(candidate => (
                      <button type="button" className="generation-reference-picker-card" key={candidate.id} onClick={() => openLibraryItem(candidate).catch(() => undefined)} disabled={pickerBusy}>
                        {candidate.first_image && <img src={mediaUrl(candidate.first_image.preview_path || candidate.first_image.thumb_path || candidate.first_image.original_path)} alt="" loading="lazy" />}
                        <span><b>{candidate.title}</b><em>{t('chooseImage')}</em></span>
                      </button>
                    ))}
                  </div>
                </>
              )}
              {referencePicker === 'library' && libraryItem && (
                <>
                  <button ref={libraryItemBackRef} className="generation-reference-back" type="button" onClick={() => setLibraryItem(undefined)}><ArrowLeft size={15} /> {t('backToLibrary')}</button>
                  <h4>{libraryItem.title}</h4>
                  <div className="generation-reference-picker-grid images">
                    {libraryItem.images.map(image => {
                      const selected = editAttachments.some(attachment => attachment.imageId === image.id);
                      return (
                        <button type="button" className={`generation-reference-picker-card${selected ? ' is-selected' : ''}`} key={image.id} onClick={() => addLibraryAttachment(image, libraryItem.title)} disabled={selected || editAttachments.length >= MAX_EDIT_ATTACHMENTS}>
                          <img src={mediaUrl(image.preview_path || image.thumb_path || image.original_path)} alt="" loading="lazy" />
                          <span><b>{image.role === 'reference_image' ? t('reference') : t('result')}</b><em>{selected ? t('selected') : t('addReference')}</em></span>
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
                        <span><b>{jobPrompt(job) || t('generatedResult')}</b><em>{selected ? t('selected') : t('generatedResult')}</em></span>
                      </button>
                    );
                  })}
                  {!pickerBusy && recentJobs.length === 0 && <p className="muted">{t('noRecentResults')}</p>}
                </div>
              )}
              <div className="generation-reference-picker-footer">
                <button className="primary" type="button" onClick={closeReferencePicker}>{t('doneSelected').replace('${count}', String(editAttachments.length))}</button>
              </div>
            </section>
          </div>
        ), document.body)}

        {showHistoryDrawer && (
          <>
          <div className={`generation-history-scrim${isHistoryDrawerClosing ? ' is-closing' : ''}`} aria-hidden="true" onClick={closeHistoryDrawer} />
          <aside ref={historyDrawerRef} className={`generation-history-drawer open${isHistoryDrawerClosing ? ' is-closing' : ''}`} role="dialog" aria-modal="true" aria-label={t('recentGenerations')} tabIndex={-1} onKeyDown={handleHistoryDrawerKeyDown}>
            <div className="drawer-head">
              <div>
                <p className="drawer-eyebrow">{t('history')}</p>
                <h3>{t('recentGenerations')}</h3>
              </div>
              <button className="modal-icon-button" onClick={closeHistoryDrawer} aria-label={t('close')}><X size={20} strokeWidth={2.25} /></button>
            </div>
            {visibleJobs.length === 0 && <p className="muted">{t('noGenerationJobs')}</p>}
            {visibleJobs.map(job => (
              <button key={job.id} className={`generation-history-item status-${job.status}`} onClick={() => previewHistoryJob(job)} aria-label={`${statusLabel(job.status, t, isUsedAsGenerationReference(job))} ${t('result')}, ${jobAspectRatio(job)}, ${jobQuality(job)}, ${jobModel(job)}`}>
                <span className="generation-history-media">
                  {jobResultUrl(job) ? <img src={jobResultUrl(job)} alt="" /> : <span className="generation-history-placeholder">{statusLabel(job.status, t, isUsedAsGenerationReference(job))}</span>}
                </span>
                <span className="generation-history-status-grid" aria-hidden="true">
                  <span className="generation-history-cell"><b>{t('queueAspectRatio')}</b><em>{optionLabel(ASPECT_RATIO_OPTIONS, jobAspectRatio(job), t)}</em></span>
                  <span className="generation-history-cell"><b>{t('queueQuality')}</b><em>{optionLabel(QUALITY_OPTIONS, jobQuality(job), t)}</em></span>
                  <span className="generation-history-cell"><b>{t('queueModel')}</b><em>{jobModel(job)}</em></span>
                  <span className="generation-history-cell"><b>{t('queueStatus')}</b><em>{statusLabel(job.status, t, isUsedAsGenerationReference(job))}</em></span>
                </span>
              </button>
            ))}
          </aside>
          </>
        )}

         {reviewJob && metadataDraft && (
           <section
             ref={element => { metadataPanelRef.current = element; saveAsNewDialogRef.current = element; }}
             tabIndex={-1}
             className={`generation-save-view${isSavePanelClosing ? ' is-closing' : ''}`}
             role="dialog"
             aria-modal="true"
             aria-label={t('saveGeneratedImageAsNew')}
             onKeyDown={handleSaveAsNewDialogKeyDown}
           >
            <div className="drawer-head generation-save-head">
              <div>
                <p className="drawer-eyebrow">{t('referenceDetails')}</p>
                <h3>{generationResultPosition(reviewJob) ? `${t('result')} ${generationResultPosition(reviewJob)?.index} / ${generationResultPosition(reviewJob)?.total}` : t('result')}</h3>
              </div>
            </div>
            <div className="save-new-metadata-grid">
              {jobResultUrl(reviewJob) && <img src={jobResultUrl(reviewJob)} alt={t('saveGeneratedResultPreview')} />}
              <div className="save-new-fields">
                {renderReferenceTray(jobAttachments(reviewJob), true)}
                <SuggestedTitleField value={metadataDraft.title || ''} promptText={metadataDraft.prompts?.[0]?.text || ''} t={t} onChange={title => updateMetadataDraft({ title })} autoFocus />
                <label><span>{t('collection')}</span><input list="save-new-collection-suggestions" value={metadataDraft.cluster_name || ''} onChange={event => updateMetadataDraft({ cluster_name: event.currentTarget.value })} /></label>
                <datalist id="save-new-collection-suggestions">
                  {filteredMetadataClusters.map(collection => <option key={collection.id} value={collection.name} />)}
                </datalist>
                <label><span>{t('libraryModelLabel')}</span><input value={metadataDraft.model || ''} onChange={event => updateMetadataDraft({ model: event.currentTarget.value })} /></label>
                 <label><span>{t('tags')}</span><input list="save-new-tag-suggestions" placeholder={t('tagsPlaceholder')} value={metadataTagsText} onChange={event => { setMetadataTagsText(event.currentTarget.value); setMetadataTagQuery(event.currentTarget.value.split(',').pop()?.trim() || ''); }} /></label>
                <datalist id="save-new-tag-suggestions">
                  {filteredMetadataTags.map(tag => <option key={tag.id} value={tag.name} />)}
                </datalist>
                {filteredMetadataTags.length > 0 && <div className="tag-suggestions" aria-label={t('existingTagSuggestions')}>
                  {filteredMetadataTags.map(tag => <button type="button" key={tag.id} onClick={() => addSuggestedMetadataTag(tag.name)}>#{tag.name}</button>)}
                </div>}
                <label className="save-new-prompt-field"><span className="prompt-field-title">{t('promptText')} <span className="save-new-language-pills" aria-label={t('originalPromptLanguage')}><span>{t('origin')}</span>{SAVE_NEW_LANGUAGE_OPTIONS.map(language => <button type="button" key={language.value} className={`origin-marker ${metadataDraft.prompts?.[0]?.language === language.value ? 'active' : ''}`} onClick={() => updateMetadataPromptLanguage(language.value)}>{t(language.labelKey).replace(/ prompt$/i, '')}</button>)}</span></span><textarea value={metadataDraft.prompts?.[0]?.text || ''} onChange={event => updatePromptDraft(event.currentTarget.value)} /></label>
                <label><span>{t('notes')}</span><textarea value={metadataDraft.notes || ''} onChange={event => updateMetadataDraft({ notes: event.currentTarget.value })} /></label>
                <div className="generation-locked-record">
                  <strong>{t('generationRecord')}</strong>
                  <dl>
                    <div><dt>{t('providers')}</dt><dd>{providers.find(providerStatus => providerStatus.provider === reviewJob.provider)?.display_name || (reviewJob.provider === 'openai_codex_oauth_native' ? 'ChatGPT / Codex OAuth' : t('providers'))}</dd></div>
                    <div><dt>{t('queueModel')}</dt><dd>{jobModel(reviewJob)}</dd></div>
                    {reviewJob.source_item_id && <div><dt>{t('originalItem')}</dt><dd>{reviewJob.source_item_id === item?.id ? item.title : t('localReference')}</dd></div>}
                    {generationResultPosition(reviewJob) && <div><dt>{t('batchPosition')}</dt><dd>{generationResultPosition(reviewJob)?.index} / {generationResultPosition(reviewJob)?.total}</dd></div>}
                  </dl>
                </div>
              </div>
            </div>
            <footer className="generation-save-actions">
              <button className="secondary" onClick={closeSaveAsNewReview} disabled={busy}>{t('cancel')}</button>
              <button className="primary" onClick={acceptAsNew} disabled={busy}>{batchReviewSession && generationReviewNext(jobs, batchReviewSession, reviewJob.id) ? t('saveAndContinue') : t('confirmSave')}</button>
            </footer>
          </section>
        )}
        {message && !selectedStageJob && <p className="provider-message generation-toast">{message}</p>}
      </section>
    </div>
  );
}
