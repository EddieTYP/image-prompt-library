import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, Clock3, ImageOff, ImagePlus, ListTodo, Maximize2, Trash2, X, XCircle } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import type { GenerationJobRecord, GenerationJobSetRecord, GenerationJobStatusCounts, GenerationProviderQueueState } from '../types';
import { generationFailure } from '../utils/generationFailures';
import { providerPauseSeconds } from '../utils/generationSets';
import { mapGenerationRetryJob, rememberGenerationReviewOpenContext, resolveGenerationRetryGroup } from '../utils/generationSiblings';
import type { Translator } from '../utils/i18n';

function isActive(job: GenerationJobRecord) {
  return job.status === 'queued' || job.status === 'running';
}

function hasDisplayableResult(job: GenerationJobRecord) {
  return Boolean(job.result_path && !['discarded', 'cancelled', 'failed'].includes(job.status));
}

function statusIcon(job: GenerationJobRecord) {
  if (isActive(job)) return <Clock3 size={16} />;
  if (job.status === 'succeeded') return <ImagePlus size={16} />;
  if (job.status === 'failed') return <XCircle size={16} />;
  return <CheckCircle2 size={16} />;
}

function statusLabel(job: GenerationJobRecord, t: Translator, isUsedAsGenerationReference = false) {
  if (job.status === 'queued') return t('queueQueued');
  if (job.status === 'running') return t('queueRunning');
  if (job.status === 'succeeded') return isUsedAsGenerationReference ? t('queueUsedAsReference') : t('queueReady');
  if (job.status === 'failed') return t('queueFailed');
  if (job.status === 'accepted') return t('queueSaved');
  if (job.status === 'discarded') return t('queueDiscarded');
  if (job.status === 'cancelled') return t('queueCancelled');
  return job.status;
}

export type GenerationQueueBatchCard = {
  generationGroupId: string;
  jobs: GenerationJobRecord[];
  total: number;
  waitingReview: number;
  accepted: number;
  active: number;
  discarded: number;
  failed: number;
  cancelled: number;
  previews: GenerationJobRecord[];
  previewOverflow: number;
  retryAdjustments: Array<{ status: string; delta: -1 | 1 }>;
};

/** Group the already-loaded jobs page without fetching per-batch details. */
export function groupGenerationQueueJobs(jobs: GenerationJobRecord[], previewLimit = 3): GenerationQueueBatchCard[] {
  const supersededOriginalIds = new Set<string>();
  const jobsById = new Map(jobs.map(job => [job.id, job]));
  const backendCountedJobIds = new Set(
    jobs.filter(job => Boolean(job.generation_group_id)).map(job => job.id),
  );
  const retryResolutions = new Map<string, ReturnType<typeof resolveGenerationRetryGroup>>();
  jobs.forEach(job => {
    const resolution = resolveGenerationRetryGroup(job, jobs);
    if (!resolution) return;
    retryResolutions.set(job.id, resolution);
    resolution.ancestorIds.forEach(ancestorId => supersededOriginalIds.add(ancestorId));
  });
  const associatedJobs = jobs
    .filter(job => !supersededOriginalIds.has(job.id))
    .map(job => {
      if (job.generation_group_id) return job;
      const resolution = retryResolutions.get(job.id);
      return resolution ? { ...job, ...resolution.fields } : job;
    });
  const groups = new Map<string, GenerationJobRecord[]>();
  associatedJobs.forEach(job => {
    if (!job.generation_group_id) return;
    const existing = groups.get(job.generation_group_id) || [];
    existing.push(job);
    groups.set(job.generation_group_id, existing);
  });
  return Array.from(groups, ([generationGroupId, groupedJobs]) => {
    const previews = groupedJobs.filter(hasDisplayableResult).slice(0, previewLimit);
    const adjustedAncestorIds = new Set<string>();
    const retryAdjustments = groupedJobs.flatMap(job => {
      const resolution = retryResolutions.get(job.id);
      if (!resolution) return [];
      const adjustments: GenerationQueueBatchCard['retryAdjustments'] = resolution.ancestorIds.flatMap(ancestorId => {
        const ancestor = jobsById.get(ancestorId);
        if (ancestor?.generation_group_id !== generationGroupId || adjustedAncestorIds.has(ancestorId)) return [];
        adjustedAncestorIds.add(ancestorId);
        return [{ status: ancestor.status, delta: -1 as const }];
      });
      const oldestLoadedAncestor = resolution.ancestorIds.length > 0
        ? jobsById.get(resolution.ancestorIds[resolution.ancestorIds.length - 1])
        : job;
      const omittedAncestorId = oldestLoadedAncestor?.metadata?.retry_of_generation_job_id;
      const omittedAncestorStatus = oldestLoadedAncestor?.metadata?.retry_reason === 'failed_retry'
        ? 'failed'
        : oldestLoadedAncestor?.metadata?.retry_reason === 'discard_and_retry' ? 'discarded' : undefined;
      if (typeof omittedAncestorId === 'string' && !jobsById.has(omittedAncestorId)
        && !adjustedAncestorIds.has(omittedAncestorId) && omittedAncestorStatus) {
        adjustedAncestorIds.add(omittedAncestorId);
        adjustments.push({ status: omittedAncestorStatus, delta: -1 });
      }
      if (!backendCountedJobIds.has(job.id)) {
        adjustments.push({ status: job.status, delta: 1 });
      }
      return adjustments;
    });
    return {
      generationGroupId,
      jobs: groupedJobs,
      total: Math.max(groupedJobs.length, ...groupedJobs.map(job => job.generation_group_size || 0)),
      waitingReview: groupedJobs.filter(job => job.status === 'succeeded').length,
      accepted: groupedJobs.filter(job => job.status === 'accepted').length,
      active: groupedJobs.filter(isActive).length,
      discarded: groupedJobs.filter(job => job.status === 'discarded').length,
      failed: groupedJobs.filter(job => job.status === 'failed').length,
      cancelled: groupedJobs.filter(job => job.status === 'cancelled').length,
      previews,
      previewOverflow: Math.max(0, groupedJobs.filter(hasDisplayableResult).length - previews.length),
      retryAdjustments,
    };
  }).filter(group => group.total > 1);
}

export function generationQueueBatchCounts(group: GenerationQueueBatchCard, set?: GenerationJobSetRecord) {
  if (!set) {
    return {
      total: group.total,
      active: group.active,
      waitingReview: group.waitingReview,
      accepted: group.accepted,
      discarded: group.discarded,
      failed: group.failed,
      cancelled: group.cancelled,
    };
  }
  const representedSlots = new Set(group.jobs
    .map(job => job.generation_group_index)
    .filter(index => typeof index === 'number' && Number.isInteger(index) && index >= 1 && index <= set.total));
  // Complete slot coverage makes the collapsed retry jobs authoritative.
  if (group.retryAdjustments.length > 0 && group.total === set.total
    && group.jobs.length === set.total && representedSlots.size === set.total) {
    return {
      total: set.total,
      active: group.active,
      waitingReview: group.waitingReview,
      accepted: group.accepted,
      discarded: group.discarded,
      failed: group.failed,
      cancelled: group.cancelled,
    };
  }
  const counts = {
    total: set.total,
    active: set.queued + set.running,
    waitingReview: set.succeeded,
    accepted: set.accepted,
    discarded: set.discarded,
    failed: set.failed,
    cancelled: set.cancelled,
  };
  const bucket = (status: string) => {
    if (status === 'queued' || status === 'running') return 'active' as const;
    if (status === 'succeeded') return 'waitingReview' as const;
    if (status === 'accepted') return 'accepted' as const;
    if (status === 'discarded') return 'discarded' as const;
    if (status === 'failed') return 'failed' as const;
    if (status === 'cancelled') return 'cancelled' as const;
    return undefined;
  };
  group.retryAdjustments.forEach(({ status, delta }) => {
    const statusBucket = bucket(status);
    if (statusBucket) counts[statusBucket] = Math.max(0, counts[statusBucket] + delta);
  });
  return counts;
}

export function generationQueueStatusCounts(jobs: GenerationJobRecord[], statusCounts?: GenerationJobStatusCounts) {
  return {
    waitingReview: statusCounts?.succeeded ?? jobs.filter(job => job.status === 'succeeded').length,
    accepted: statusCounts?.accepted ?? jobs.filter(job => job.status === 'accepted').length,
    discarded: statusCounts?.discarded ?? jobs.filter(job => job.status === 'discarded').length,
    failed: statusCounts?.failed ?? jobs.filter(job => job.status === 'failed').length,
    cancelled: statusCounts?.cancelled ?? jobs.filter(job => job.status === 'cancelled').length,
  };
}

function isUsedAsGenerationReference(job: GenerationJobRecord, jobs: GenerationJobRecord[]) {
  if (!job.result_path) return false;
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
}

function canOpenJob(job: GenerationJobRecord) {
  return job.status !== 'discarded';
}

const STALE_RUNNING_JOB_MS = 10 * 60 * 1000;
const QUEUE_EXIT_WATCHDOG_MS = 260;
const QUEUE_PAGE_SIZE = 100;
const QUEUE_MAX_WINDOW = 1000;
const QUEUE_FOCUSABLE_SELECTOR = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function retriedByJobId(job: GenerationJobRecord) {
  const value = job.metadata?.retried_by_generation_job_id;
  return typeof value === 'string' && value ? value : '';
}

function canRetryFailedJob(job: GenerationJobRecord) {
  return job.status === 'failed' && !retriedByJobId(job);
}

function canDiscardTransientResult(job: GenerationJobRecord) {
  return Boolean(job.status === 'succeeded' && !job.accepted_image_id && job.result_path && job.result_path?.startsWith(`generation-results/${job.id}/`));
}

function jobResultUrl(job: GenerationJobRecord) {
  return hasDisplayableResult(job) ? mediaUrl(job.result_path as string) : '';
}

function jobParameter(job: GenerationJobRecord, key: string, fallback: string) {
  const value = job.parameters?.[key];
  return typeof value === 'string' && value ? value : fallback;
}

function jobAspectRatio(job: GenerationJobRecord) {
  return jobParameter(job, 'requested_aspect_ratio', 'auto');
}

function jobQuality(job: GenerationJobRecord) {
  const value = jobParameter(job, 'quality', 'default');
  return value === 'standard' ? 'medium' : value;
}

function jobModel(job: GenerationJobRecord) {
  return job.model || jobParameter(job, 'orchestrator_model', 'default');
}

function isStaleRunningJob(job: GenerationJobRecord) {
  if (job.status !== 'running') return false;
  const started = Date.parse(job.started_at || job.updated_at || job.created_at);
  return Number.isFinite(started) && Date.now() - started > STALE_RUNNING_JOB_MS;
}

function mergeGenerationJobs(current: GenerationJobRecord[], incoming: GenerationJobRecord[]) {
  const updates = new Map(incoming.map(job => [job.id, job]));
  return [...incoming, ...current.filter(job => !updates.has(job.id))];
}

export default function GenerationQueueDrawer({
  t,
  open,
  refreshKey,
  onOpen,
  onClose,
  onOpenJob,
  onOpenProviders,
}: {
  t: Translator;
  open: boolean;
  refreshKey: number;
  onOpen: () => void;
  onClose: () => void;
  onOpenJob: (job: GenerationJobRecord) => void;
  onOpenProviders: () => void;
}) {
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [generationSets, setGenerationSets] = useState<GenerationJobSetRecord[]>([]);
  const [providerQueueStates, setProviderQueueStates] = useState<GenerationProviderQueueState[]>([]);
  const [statusCounts, setStatusCounts] = useState<GenerationJobStatusCounts>();
  const [jobTotal, setJobTotal] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [cancelBusyIds, setCancelBusyIds] = useState<Set<string>>(() => new Set());
  const [retryBusyIds, setRetryBusyIds] = useState<Set<string>>(() => new Set());
  const [markFailedBusyIds, setMarkFailedBusyIds] = useState<Set<string>>(() => new Set());
  const [discardBusyIds, setDiscardBusyIds] = useState<Set<string>>(() => new Set());
  const [cancelSetBusyIds, setCancelSetBusyIds] = useState<Set<string>>(() => new Set());
  const [openingSetId, setOpeningSetId] = useState<string>();
  const [windowLimit, setWindowLimit] = useState(QUEUE_PAGE_SIZE);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [queueClock, setQueueClock] = useState(() => Date.now());
  const [hasLoaded, setHasLoaded] = useState(false);
  const windowLimitRef = useRef(QUEUE_PAGE_SIZE);
  const refreshRequestRef = useRef(0);
  const openSetRequestRef = useRef(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const refresh = useCallback(async (limit = windowLimitRef.current) => {
    const requestId = refreshRequestRef.current + 1;
    refreshRequestRef.current = requestId;
    try {
      const result = await api.generationJobs({ limit });
      if (refreshRequestRef.current !== requestId) return;
      setJobs(result.jobs);
      setJobTotal(result.total);
      setStatusCounts(result.status_counts);
      setGenerationSets(result.generation_sets || []);
      setProviderQueueStates(result.provider_queue_states || []);
      setLoadError('');
      setHasLoaded(true);
    } catch (error) {
      if (refreshRequestRef.current !== requestId) return;
      setLoadError(error instanceof Error ? error.message : t('queueLoadFailed'));
      setHasLoaded(true);
    }
  }, [t]);

  const hasActiveWork = Boolean(
    (statusCounts?.queued || 0)
    + (statusCounts?.running || 0)
    + generationSets.filter(set => set.total > 1).reduce((total, set) => total + set.remaining, 0),
  );
  useEffect(() => {
    refresh().catch(() => undefined);
    if (!open && !hasActiveWork) return undefined;
    const timer = window.setInterval(() => refresh().catch(() => undefined), 6000);
    return () => window.clearInterval(timer);
  }, [hasActiveWork, open, refresh, refreshKey]);

  useEffect(() => {
    if (!open || !providerQueueStates.some(state => providerPauseSeconds(state) > 0)) return undefined;
    setQueueClock(Date.now());
    const timer = window.setInterval(() => setQueueClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open, providerQueueStates]);

  useEffect(() => {
    if (!open) return undefined;
    const frame = window.requestAnimationFrame(() => {
      drawerRef.current?.querySelector<HTMLElement>(QUEUE_FOCUSABLE_SELECTOR)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (open) return;
    openSetRequestRef.current += 1;
    setOpeningSetId(undefined);
  }, [open]);

  useEffect(() => () => {
    openSetRequestRef.current += 1;
  }, []);

  const closeDrawer = (restoreFocus = true) => {
    openSetRequestRef.current += 1;
    const drawer = drawerRef.current;
    let restored = false;
    let fallback: number | undefined;
    const restore = () => {
      if (restored) return;
      restored = true;
      if (drawer) drawer.removeEventListener('transitionend', handleTransitionEnd);
      if (fallback !== undefined) window.clearTimeout(fallback);
      if (restoreFocus) triggerRef.current?.focus({ preventScroll: true });
    };
    const handleTransitionEnd = (event: TransitionEvent) => {
      if (event.target === drawer) restore();
    };
    if (restoreFocus && drawer && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      drawer.addEventListener('transitionend', handleTransitionEnd);
      fallback = window.setTimeout(restore, QUEUE_EXIT_WATCHDOG_MS);
    }
    onCloseRef.current();
    if (restoreFocus && (!drawer || window.matchMedia('(prefers-reduced-motion: reduce)').matches)) {
      window.requestAnimationFrame(restore);
    }
  };

  const handleQueueKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeDrawer();
      return;
    }
    if (event.key !== 'Tab' || !drawerRef.current) return;
    const focusable = Array.from(drawerRef.current.querySelectorAll<HTMLElement>(QUEUE_FOCUSABLE_SELECTOR))
      .filter(element => element.getClientRects().length > 0 || element === document.activeElement);
    if (focusable.length === 0) {
      event.preventDefault();
      drawerRef.current.focus({ preventScroll: true });
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

  const cancelJob = async (job: GenerationJobRecord) => {
    if (!isActive(job) || cancelBusyIds.has(job.id)) return;
    setCancelBusyIds(current => new Set(current).add(job.id));
    try {
      const updated = await api.cancelGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setLoadError('');
      await refresh();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('queueCancelFailed'));
    } finally {
      setCancelBusyIds(current => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  };

  const retryJob = async (job: GenerationJobRecord) => {
    if (!canRetryFailedJob(job) || retryBusyIds.has(job.id)) return;
    setRetryBusyIds(current => new Set(current).add(job.id));
    try {
      const retry = await api.retryGenerationJob(job.id);
      setJobs(current => [retry, ...current.filter(candidate => candidate.id !== retry.id)]);
      setLoadError('');
      await refresh();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('queueRetryFailedError'));
    } finally {
      setRetryBusyIds(current => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  };

  const markFailedJob = async (job: GenerationJobRecord) => {
    if (!isStaleRunningJob(job) || markFailedBusyIds.has(job.id)) return;
    setMarkFailedBusyIds(current => new Set(current).add(job.id));
    try {
      const updated = await api.markGenerationJobFailed(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setLoadError('');
      await refresh();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('queueMarkFailedError'));
    } finally {
      setMarkFailedBusyIds(current => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  };

  const discardJob = async (job: GenerationJobRecord) => {
    if (!canDiscardTransientResult(job) || discardBusyIds.has(job.id)) return;
    const timestamp = new Date().toISOString();
    const optimisticDiscardedJob: GenerationJobRecord = {
      ...job,
      status: 'discarded',
      result_path: null,
      result_width: null,
      result_height: null,
      result_sha256: null,
      discarded_at: timestamp,
      updated_at: timestamp,
      metadata: {
        ...(job.metadata || {}),
        discarded_result_path: job.result_path,
      },
    };
    setDiscardBusyIds(current => new Set(current).add(job.id));
    setJobs(current => current.map(candidate => candidate.id === job.id ? optimisticDiscardedJob : candidate));
    try {
      const updated = await api.discardGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setLoadError('');
      void refresh();
    } catch (error) {
      setJobs(current => current.map(candidate => candidate.id === job.id ? job : candidate));
      setLoadError(error instanceof Error ? error.message : t('queueDiscardFailed'));
    } finally {
      setDiscardBusyIds(current => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  };

  const cancelRemainingGenerationSet = async (set: GenerationJobSetRecord) => {
    if (!set.remaining || cancelSetBusyIds.has(set.generation_group_id)) return;
    setCancelSetBusyIds(current => new Set(current).add(set.generation_group_id));
    try {
      const updated = await api.cancelRemainingGenerationSet(set.generation_group_id);
      setGenerationSets(current => current.map(candidate => candidate.generation_group_id === updated.generation_group_id ? updated : candidate));
      setJobs(current => mergeGenerationJobs(current, updated.jobs));
      setLoadError('');
      void refresh();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('queueCancelSetFailed'));
    } finally {
      setCancelSetBusyIds(current => {
        const next = new Set(current);
        next.delete(set.generation_group_id);
        return next;
      });
    }
  };

  const openGenerationSet = async (group: GenerationQueueBatchCard) => {
    if (openingSetId) return;
    const requestId = openSetRequestRef.current + 1;
    openSetRequestRef.current = requestId;
    setOpeningSetId(group.generationGroupId);
    try {
      let groupJobs = group.jobs;
      let expansionError: unknown;
      if (group.total > group.jobs.length) {
        try {
          const expanded = await api.generationSet(group.generationGroupId);
          if (openSetRequestRef.current !== requestId) return;
          const mergedJobs = mergeGenerationJobs(group.jobs, expanded.jobs.map(mapGenerationRetryJob));
          const mergedGroup = groupGenerationQueueJobs(mergedJobs).find(candidate => candidate.generationGroupId === group.generationGroupId);
          groupJobs = mergedGroup?.jobs || mergedJobs;
          setJobs(current => mergeGenerationJobs(current, expanded.jobs.map(mapGenerationRetryJob)));
        } catch (error) {
          expansionError = error;
        }
      }
      if (openSetRequestRef.current !== requestId) return;
      const openableJobs = groupJobs.filter(canOpenJob);
      const job = openableJobs.find(candidate => candidate.status === 'succeeded')
        || openableJobs.find(candidate => candidate.status === 'failed')
        || openableJobs.find(candidate => candidate.status === 'running')
        || openableJobs.find(candidate => candidate.status === 'queued')
        || openableJobs[0]
        || groupJobs[0];
      if (!job) throw new Error(t('queueOpenBatchFailed'));
      rememberGenerationReviewOpenContext(job.id, {
        generationGroupId: group.generationGroupId,
        generationGroupSize: Math.max(group.total, ...groupJobs.map(candidate => candidate.generation_group_size || 0)),
        jobs: groupJobs,
      });
      setLoadError(expansionError instanceof Error ? expansionError.message : '');
      onOpenJob(job);
    } catch (error) {
      if (openSetRequestRef.current === requestId) setLoadError(error instanceof Error ? error.message : t('queueOpenBatchFailed'));
    } finally {
      if (openSetRequestRef.current === requestId) setOpeningSetId(undefined);
    }
  };

  const loadOlder = async () => {
    if (loadingOlder || windowLimit >= QUEUE_MAX_WINDOW || jobs.length >= jobTotal) return;
    const nextLimit = Math.min(QUEUE_MAX_WINDOW, windowLimit + QUEUE_PAGE_SIZE);
    setLoadingOlder(true);
    windowLimitRef.current = nextLimit;
    setWindowLimit(nextLimit);
    try {
      await refresh(nextLimit);
    } finally {
      setLoadingOlder(false);
    }
  };

  const renderFailedJob = (job: GenerationJobRecord) => {
     const failure = generationFailure(job, t);
    const retryId = retriedByJobId(job);
    const retry = retryId ? jobs.find(candidate => candidate.id === retryId) : undefined;
    return (
      <article className="generation-queue-failure status-failed" key={job.id}>
        <button type="button" className="generation-queue-failure-summary" onClick={() => onOpenJob(job)}>
          <span className="generation-queue-failure-icon" aria-hidden="true">{statusIcon(job)}</span>
          <span className="generation-queue-failure-copy">
            <strong>{retryId ? t('queueRetried') : failure.title}</strong>
            <span>{failure.guidance}</span>
            <small>{job.edited_prompt_text || job.prompt_text}</small>
          </span>
        </button>
        <div className="generation-queue-failure-actions" aria-label={t('queueFailedActions')}>
          {failure.kind === 'auth_required' && (
            <button type="button" className="primary" onClick={onOpenProviders}>{t('queueOpenProviders')}</button>
          )}
          {canRetryFailedJob(job) && (
            <button
              type="button"
              className={failure.kind === 'auth_required' ? 'secondary' : 'primary'}
              onClick={() => retryJob(job).catch(() => undefined)}
              disabled={retryBusyIds.has(job.id)}
            >{t('queueRetry')}</button>
          )}
          {retryId && (
            <button type="button" className="secondary" onClick={() => onOpenJob(retry || job)}>{t('queueOpenRetryJob')}</button>
          )}
        </div>
      </article>
    );
  };

  const counts = useMemo(() => {
    const running = statusCounts?.running ?? jobs.filter(job => job.status === 'running').length;
    const queued = statusCounts?.queued ?? jobs.filter(job => job.status === 'queued').length;
    return {
      running,
      queued,
      active: running + queued,
      ready: statusCounts?.succeeded ?? jobs.filter(job => job.status === 'succeeded').length,
      failed: statusCounts?.failed ?? jobs.filter(job => job.status === 'failed').length,
    };
  }, [jobs, statusCounts]);
  const queuePersistentCounts = useMemo(() => generationQueueStatusCounts(jobs, statusCounts), [jobs, statusCounts]);
  const queueStatusItems = [
    { key: 'active', count: counts.running + counts.queued, label: t('queueInProgress') },
    { key: 'ready', count: queuePersistentCounts.waitingReview, label: t('queueReady') },
    { key: 'saved', count: queuePersistentCounts.accepted, label: t('queueSaved') },
    { key: 'discarded', count: queuePersistentCounts.discarded, label: t('queueDiscarded') },
    { key: 'failed', count: queuePersistentCounts.failed, label: t('queueFailed') },
    { key: 'cancelled', count: queuePersistentCounts.cancelled, label: t('queueCancelled') },
  ].filter(item => item.count > 0);
  const generationBatchCards = useMemo(() => groupGenerationQueueJobs(jobs), [jobs]);
  const groupedJobIds = useMemo(() => new Set(generationBatchCards.flatMap(group => group.jobs.map(job => job.id))), [generationBatchCards]);
  const hasActiveGenerationSet = generationBatchCards.some(group => group.jobs.some(isActive));
  const hasSignal = counts.active + counts.ready + counts.failed > 0 || hasActiveGenerationSet;
  const pausedProviderQueues = providerQueueStates
    .map(state => ({ state, seconds: providerPauseSeconds(state, queueClock) }))
    .filter(entry => entry.seconds > 0);

  const sections = [
    { key: 'active', title: t('queueInProgress'), jobs: jobs.filter(job => !groupedJobIds.has(job.id) && isActive(job)) },
    { key: 'ready', title: t('queueReadyForReview'), jobs: jobs.filter(job => !groupedJobIds.has(job.id) && job.status === 'succeeded') },
    { key: 'failed', title: t('queueNeedsAttention'), jobs: jobs.filter(job => !groupedJobIds.has(job.id) && job.status === 'failed') },
    { key: 'recent', title: t('queueRecent'), jobs: jobs.filter(job => !groupedJobIds.has(job.id) && ['accepted', 'discarded', 'cancelled'].includes(job.status)) },
  ];
  const visibleSections = sections.filter(section => section.jobs.length > 0);
  const hasHistoricalActivity = jobTotal > 0 || Object.values(statusCounts || {}).some(count => Number(count) > 0);
  const hasQueueContent = pausedProviderQueues.length > 0 || generationBatchCards.length > 0 || visibleSections.length > 0 || hasHistoricalActivity;

  const trigger = (
    <button
        ref={triggerRef}
        className={`generation-queue-trigger ${hasSignal ? 'has-signal' : ''}`}
        onClick={open ? () => closeDrawer() : onOpen}
        aria-label={t('workQueue')}
        aria-expanded={open}
        aria-controls="generation-work-queue"
      >
        <ListTodo size={18} />
        {(counts.active > 0 || hasActiveGenerationSet) && <span className="queue-dot active" aria-label={t('queueActiveJobs')} />}
        {counts.ready > 0 && <span className="queue-dot ready" aria-label={t('queueReadyResults')} />}
        {counts.failed > 0 && <span className="queue-dot failed" aria-label={t('queueFailedJobs')} />}
      </button>
  );
  const queueLayer = (
    <>
      {open && <div className="generation-queue-scrim" aria-hidden="true" onClick={() => closeDrawer()} />}
      <aside
        id="generation-work-queue"
        ref={drawerRef}
        className={`generation-queue-drawer${open ? ' open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="generation-work-queue-title"
        aria-hidden={!open}
        inert={!open}
        tabIndex={-1}
        onKeyDown={handleQueueKeyDown}
      >
          <div className="drawer-head">
            <h2 id="generation-work-queue-title">{t('workQueue')}</h2>
            <button className="modal-icon-button" onClick={() => closeDrawer()} aria-label={t('close')}><X size={20} strokeWidth={2.25} /></button>
          </div>
          {!hasLoaded && !loadError && <p className="muted queue-loading" role="status">{t('queueLoading')}</p>}
          {loadError && <p className="error" role="alert">{loadError}</p>}
          {hasLoaded && hasQueueContent && queueStatusItems.length > 0 && (
            <ul className="queue-summary generation-queue-persistent-counts">
              {queueStatusItems.map(item => (
                <li key={item.key} className={`queue-status-${item.key}`}>
                  <b>{item.count}</b> {item.label.toLocaleLowerCase()}
                </li>
              ))}
            </ul>
          )}
          {hasLoaded && jobTotal > jobs.length && (
            <div className="queue-window">
              <p className="muted queue-window-note">{t('queueShowingLatest').replace('${shown}', String(jobs.length)).replace('${total}', String(jobTotal))}</p>
              {windowLimit < QUEUE_MAX_WINDOW && (
                <button type="button" className="queue-load-older" onClick={() => loadOlder().catch(() => undefined)} disabled={loadingOlder}>
                  {loadingOlder ? t('queueLoadingOlder') : t('queueLoadOlder')}
                </button>
              )}
            </div>
          )}
          {hasLoaded && !hasQueueContent && !loadError && (
            <div className="generation-queue-empty">
              <span className="generation-queue-empty-icon" aria-hidden="true"><ListTodo size={22} /></span>
              <strong>{t('noGenerationActivity')}</strong>
              <p>{t('generationActivityHelp')}</p>
            </div>
          )}
          {pausedProviderQueues.map(({ state, seconds }) => (
             <section className="generation-provider-pause queue" key={state.provider} aria-label={`${state.provider}: ${t('queueProviderPaused')} ${state.paused_until || ''}`}>
              <strong>{t('queueProviderPaused')}</strong>
              <span aria-hidden="true">{t('queueRateLimitedResume').replace('${seconds}', String(seconds))}</span>
               {state.paused_until && <time className="sr-only" dateTime={state.paused_until}>{t('pausedUntil').replace('${time}', state.paused_until)}</time>}
            </section>
          ))}
          {generationBatchCards.length > 0 && (
            <section className="generation-queue-section generation-set-section">
              <h3>{t('queueGenerationSets')}</h3>
              {generationBatchCards.map(group => {
                const set = generationSets.find(candidate => candidate.generation_group_id === group.generationGroupId);
                const summary = generationQueueBatchCounts(group, set);
                return (
                <article className="generation-set-card generation-queue-batch-card" key={group.generationGroupId}>
                  <div className="generation-set-progress-head">
                    <strong>{t('queueGenerationSet')}</strong>
                    <span>{summary.total} {t('result').toLowerCase()}</span>
                  </div>
                  {group.previews.length > 0 ? (
                    <div className="generation-queue-batch-previews" aria-label={`${group.previews.length}${group.previewOverflow ? ` +${group.previewOverflow}` : ''} ${t('result')}`}>
                      {open
                        ? group.previews.map(job => <img key={job.id} src={jobResultUrl(job)} alt="" loading="lazy" decoding="async" />)
                        : <span className="generation-queue-batch-preview-closed">{group.previews.length}</span>}
                      {group.previewOverflow > 0 && <span className="generation-queue-batch-overflow">+{group.previewOverflow}</span>}
                    </div>
                  ) : <div className="generation-queue-batch-placeholder" role="img" aria-label={t('noImage')} title={t('noImage')}><ImageOff size={17} aria-hidden="true" /></div>}
                   <p className="generation-queue-batch-counts">
                     {summary.active > 0 && <span>{summary.active} {t('queueInProgress').toLowerCase()}</span>}
                     {summary.waitingReview > 0 && <span>{summary.waitingReview} {t('queueReady').toLowerCase()}</span>}
                    {summary.accepted > 0 && <span>{summary.accepted} {t('queueSaved').toLowerCase()}</span>}
                    {summary.discarded > 0 && <span>{summary.discarded} {t('queueDiscarded').toLowerCase()}</span>}
                    {summary.failed > 0 && <span>{summary.failed} {t('queueFailed').toLowerCase()}</span>}
                    {summary.cancelled > 0 && <span>{summary.cancelled} {t('queueCancelled').toLowerCase()}</span>}
                  </p>
                  <div className="generation-set-actions">
                    <button
                      type="button"
                      className="generation-open-set"
                      onClick={() => openGenerationSet(group).catch(() => undefined)}
                      disabled={openingSetId === group.generationGroupId}
                    >{t('queueOpenBatch')}</button>
                    {set && set.remaining > 0 && (
                      <button
                        type="button"
                        className="generation-cancel-remaining"
                        onClick={() => cancelRemainingGenerationSet(set).catch(() => undefined)}
                        disabled={cancelSetBusyIds.has(set.generation_group_id)}
                      >{t('queueCancelRemaining').replace('${remaining}', String(set.remaining))}</button>
                    )}
                  </div>
                </article>
                );
              })}
            </section>
          )}
          {visibleSections.map(section => (
            <section className="generation-queue-section" key={section.key}>
              <h3>{section.title}</h3>
              {section.jobs.map(job => (
                section.key === 'failed' && job.status === 'failed' ? renderFailedJob(job) : section.key === 'ready' && job.status === 'succeeded' ? (
                  <article
                    key={job.id}
                    className="generation-queue-result generation-history-item status-succeeded"
                  >
                    <button
                      type="button"
                      className="generation-queue-result-main"
                      onClick={() => onOpenJob(job)}
                       aria-label={`${statusLabel(job, t, isUsedAsGenerationReference(job, jobs))} ${t('result')}, ${jobAspectRatio(job)}, ${jobQuality(job)}, ${jobModel(job)}`}
                    >
                      <span className="generation-history-media">
                        {open && jobResultUrl(job) ? <img src={jobResultUrl(job)} alt="" loading="lazy" decoding="async" /> : <span className="generation-history-placeholder">{statusLabel(job, t, isUsedAsGenerationReference(job, jobs))}</span>}
                      </span>
                      <span className="generation-history-status-grid" aria-hidden="true">
                        <span className="generation-history-cell"><b>{t('queueAspectRatio')}</b><em>{jobAspectRatio(job)}</em></span>
                        <span className="generation-history-cell"><b>{t('queueQuality')}</b><em>{jobQuality(job)}</em></span>
                        <span className="generation-history-cell"><b>{t('queueModel')}</b><em>{jobModel(job)}</em></span>
                        <span className="generation-history-cell"><b>{t('queueStatus')}</b><em>{statusLabel(job, t, isUsedAsGenerationReference(job, jobs))}</em></span>
                      </span>
                    </button>
                    <span className="generation-queue-preview-actions">
                      <button type="button" className="generation-queue-quick-expand" onClick={() => onOpenJob(job)} aria-label={t('queueExpandResult')} title={t('queueExpandResult')}>
                        <Maximize2 size={15} aria-hidden="true" />
                      </button>
                      {canDiscardTransientResult(job) && (
                        <button
                          type="button"
                          className="generation-queue-quick-discard"
                          onClick={() => discardJob(job).catch(() => undefined)}
                          disabled={discardBusyIds.has(job.id)}
                          aria-label={t('queueDiscardResult')}
                          title={t('queueDiscardResult')}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                        </button>
                      )}
                    </span>
                  </article>
                ) : (
                  <article
                    key={job.id}
                    className={`generation-queue-row status-${job.status}`}
                  >
                    <button
                      type="button"
                      className="generation-queue-row-main"
                      onClick={() => onOpenJob(job)}
                      disabled={!canOpenJob(job)}
                    >
                      {statusIcon(job)}
                      <span>{job.edited_prompt_text || job.prompt_text}</span>
                    </button>
                    <span className="generation-queue-row-actions">
                      <b>{statusLabel(job, t, isUsedAsGenerationReference(job, jobs))}</b>
                       {isStaleRunningJob(job) && <em className="generation-stale-copy">{t('generationStalled')}</em>}
                      {isActive(job) && (
                        <em className="generation-cancel-copy">
                          {job.status === 'running' ? t('queueRunningCancelNote') : t('queueQueuedCancelNote')}
                        </em>
                      )}
                      {isActive(job) && (
                        <button
                          type="button"
                          className="generation-queue-cancel"
                          onClick={event => {
                            event.stopPropagation();
                            cancelJob(job).catch(() => undefined);
                          }}
                          disabled={cancelBusyIds.has(job.id)}
                        >{job.status === 'running' ? t('queueStopSaving') : t('cancel')}</button>
                      )}
                      {isStaleRunningJob(job) && (
                        <button
                          type="button"
                          className="generation-queue-cancel"
                          onClick={event => {
                            event.stopPropagation();
                            markFailedJob(job).catch(() => undefined);
                          }}
                          disabled={markFailedBusyIds.has(job.id)}
                          aria-label={t('queueMarkFailed')}
                          title={t('queueMarkFailed')}
                        >{t('queueMarkFailed')}</button>
                      )}
                      {canRetryFailedJob(job) && (
                        <button
                          type="button"
                          className="generation-queue-cancel"
                          onClick={event => {
                            event.stopPropagation();
                            retryJob(job).catch(() => undefined);
                          }}
                          disabled={retryBusyIds.has(job.id)}
                          aria-label={t('queueRetryFailed')}
                          title={t('queueRetryFailed')}
                        >{t('queueRetry')}</button>
                      )}
                      {job.status === 'failed' && retriedByJobId(job) && <em>{t('queueRetried')}</em>}
                    </span>
                  </article>
                )
              ))}
            </section>
          ))}
      </aside>
    </>
  );
  return (
    <>
      {trigger}
      {typeof document === 'undefined' ? queueLayer : createPortal(queueLayer, document.body)}
    </>
  );
}
