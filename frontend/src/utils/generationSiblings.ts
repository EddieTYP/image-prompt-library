import type { GenerationJobRecord } from '../types';

export type GenerationRetryGroupFields = Pick<GenerationJobRecord, 'generation_group_id' | 'generation_group_index' | 'generation_group_size'>;

export type GenerationRetryGroupResolution = {
  fields: GenerationRetryGroupFields;
  sourceJob?: GenerationJobRecord;
  ancestorIds: string[];
};

/**
 * Read an optional batch mapping carried by a retry response. Only complete,
 * one-based slot metadata is trusted; a retry without it stays standalone.
 */
export function generationRetryGroupFields(job?: GenerationJobRecord): GenerationRetryGroupFields | undefined {
  if (!job || job.generation_group_id || typeof job.metadata?.retry_of_generation_job_id !== 'string') return undefined;
  const metadata = job.metadata || {};
  const generationGroupId = typeof metadata.generation_group_id === 'string'
    ? metadata.generation_group_id
    : typeof metadata.retry_generation_group_id === 'string' ? metadata.retry_generation_group_id : '';
  const generationGroupIndex = typeof metadata.generation_group_index === 'number'
    ? metadata.generation_group_index
    : typeof metadata.retry_generation_group_index === 'number' ? metadata.retry_generation_group_index : undefined;
  const generationGroupSize = typeof metadata.generation_group_size === 'number'
    ? metadata.generation_group_size
    : typeof metadata.retry_generation_group_size === 'number' ? metadata.retry_generation_group_size : undefined;
  if (!generationGroupId || typeof generationGroupIndex !== 'number' || typeof generationGroupSize !== 'number'
    || !Number.isInteger(generationGroupIndex) || !Number.isInteger(generationGroupSize)
    || generationGroupIndex < 1 || generationGroupSize <= 1 || generationGroupIndex > generationGroupSize) return undefined;
  return {
    generation_group_id: generationGroupId,
    generation_group_index: generationGroupIndex,
    generation_group_size: generationGroupSize,
  };
}

function explicitGenerationGroupFields(job: GenerationJobRecord): GenerationRetryGroupFields | undefined {
  if (!job.generation_group_id || !Number.isInteger(job.generation_group_index) || !Number.isInteger(job.generation_group_size)
    || (job.generation_group_index || 0) < 1 || (job.generation_group_size || 0) <= 1
    || (job.generation_group_index || 0) > (job.generation_group_size || 0)) return undefined;
  return {
    generation_group_id: job.generation_group_id,
    generation_group_index: job.generation_group_index,
    generation_group_size: job.generation_group_size,
  };
}

export function resolveGenerationRetryGroup(
  job: GenerationJobRecord,
  jobs: GenerationJobRecord[],
): GenerationRetryGroupResolution | undefined {
  const ownFields = explicitGenerationGroupFields(job) || generationRetryGroupFields(job);
  const retryOf = job.metadata?.retry_of_generation_job_id;
  if (typeof retryOf !== 'string') return undefined;
  const jobsById = new Map(jobs.map(candidate => [candidate.id, candidate]));
  const visited = new Set([job.id]);
  const ancestorIds: string[] = [];
  let parentId: string | undefined = retryOf;
  let sourceJob: GenerationJobRecord | undefined;
  let fields: GenerationRetryGroupFields | undefined = ownFields;
  while (parentId) {
    if (visited.has(parentId)) return undefined;
    visited.add(parentId);
    const parent = jobsById.get(parentId);
    if (!parent) return fields ? { fields, sourceJob, ancestorIds } : undefined;
    ancestorIds.push(parent.id);
    const parentExplicitFields = explicitGenerationGroupFields(parent);
    const parentFields = parentExplicitFields || generationRetryGroupFields(parent);
    if (!fields && parentFields) fields = parentFields;
    if (!sourceJob && parentExplicitFields) sourceJob = parent;
    const nextRetryOf = parent.metadata?.retry_of_generation_job_id;
    parentId = typeof nextRetryOf === 'string' ? nextRetryOf : undefined;
  }
  return fields ? { fields, sourceJob, ancestorIds } : undefined;
}

export function mapGenerationRetryJob(job: GenerationJobRecord): GenerationJobRecord {
  const fields = generationRetryGroupFields(job);
  return fields ? { ...job, ...fields } : job;
}

export function mapGenerationRetryJobs(jobs: GenerationJobRecord[]): GenerationJobRecord[] {
  return jobs.map(job => {
    if (job.generation_group_id) return job;
    const resolution = resolveGenerationRetryGroup(job, jobs);
    return resolution ? { ...job, ...resolution.fields } : job;
  });
}

export type GenerationSiblingNavigation = {
  siblings: GenerationJobRecord[];
  index: number;
  total: number;
  previous?: GenerationJobRecord;
  next?: GenerationJobRecord;
};

export type GenerationReviewSlot = {
  index: number;
  currentJobId?: string;
  originalJobId?: string;
  /** Session-only metadata for the item created/updated by an accepted result. */
  targetItemId?: string;
  targetItemTitle?: string;
  /** Keep the last usable result path when the API clears it on acceptance. */
  resultPath?: string;
  resolution?: 'saved' | 'attached' | 'discarded' | 'failed' | 'cancelled';
};

export type GenerationReviewSession = {
  generationGroupId: string;
  generationGroupSize: number;
  slots: GenerationReviewSlot[];
};

export type GenerationReviewOpenContext = {
  generationGroupId: string;
  generationGroupSize: number;
  jobs: GenerationJobRecord[];
};

const generationReviewOpenContexts = new Map<string, GenerationReviewOpenContext>();

/** Keep a queue-opened batch available while the standalone panel hydrates. */
export function rememberGenerationReviewOpenContext(jobId: string, context: GenerationReviewOpenContext) {
  generationReviewOpenContexts.set(jobId, context);
  if (generationReviewOpenContexts.size > 32) {
    const oldest = generationReviewOpenContexts.keys().next().value;
    if (typeof oldest === 'string') generationReviewOpenContexts.delete(oldest);
  }
}

export function generationReviewOpenContext(jobId?: string): GenerationReviewOpenContext | undefined {
  return jobId ? generationReviewOpenContexts.get(jobId) : undefined;
}

export type GenerationReviewSummary = {
  total: number;
  actionable: number;
  pendingGeneration: number;
  pendingRetry: number;
  saved: number;
  attached: number;
  discarded: number;
  failedOrCancelled: number;
  resolved: number;
  complete: boolean;
};

export type GenerationReviewSlotNavigation = {
  slots: GenerationReviewSlot[];
  index: number;
  total: number;
  previous?: GenerationReviewSlot;
  next?: GenerationReviewSlot;
};

function preferLatestGenerationJob(
  existing: GenerationJobRecord | undefined,
  candidate: GenerationJobRecord,
  currentJobId?: string,
): GenerationJobRecord {
  if (!existing || candidate.id === currentJobId) return candidate;
  if (existing.id === currentJobId) return existing;
  const createdOrder = candidate.created_at.localeCompare(existing.created_at);
  return createdOrder > 0 || (createdOrder === 0 && candidate.id.localeCompare(existing.id) > 0)
    ? candidate
    : existing;
}

function groupJobsByStableSlot(
  jobs: GenerationJobRecord[],
  generationGroupId: string,
  currentJobId?: string,
): Map<number, GenerationJobRecord> {
  const byIndex = new Map<number, GenerationJobRecord>();
  jobs.forEach(job => {
    if (job.generation_group_id !== generationGroupId || !job.generation_group_index) return;
    byIndex.set(
      job.generation_group_index,
      preferLatestGenerationJob(byIndex.get(job.generation_group_index), job, currentJobId),
    );
  });
  return byIndex;
}

export function generationResultPosition(job?: GenerationJobRecord): { index: number; total: number } | undefined {
  if (!job?.generation_group_id || !job.generation_group_size || !job.generation_group_index) return undefined;
  return { index: job.generation_group_index, total: job.generation_group_size };
}

export function isActionableGenerationResult(job?: GenerationJobRecord): boolean {
  return Boolean(job && job.status === 'succeeded' && !job.accepted_image_id && job.result_path);
}

export function createGenerationReviewSession(
  jobs: GenerationJobRecord[],
  current?: GenerationJobRecord,
): GenerationReviewSession | undefined {
  if (!current?.generation_group_id || (current.generation_group_size || 1) <= 1) return undefined;
  const generationGroupId = current.generation_group_id;
  const groupJobs = jobs.filter(job => job.generation_group_id === generationGroupId);
  const generationGroupSize = Math.max(
    current.generation_group_size || 1,
    ...groupJobs.map(job => job.generation_group_size || 0),
  );
  const byIndex = groupJobsByStableSlot(groupJobs, generationGroupId, current.id);
  const slots = Array.from({ length: generationGroupSize }, (_, offset) => {
    const index = offset + 1;
    const job = byIndex.get(index);
    return {
      index,
      currentJobId: job?.id,
      originalJobId: job?.id,
      resultPath: job?.result_path || undefined,
    };
  });
  if (current.generation_group_index && !slots[current.generation_group_index - 1]?.currentJobId) {
    slots[current.generation_group_index - 1] = {
      index: current.generation_group_index,
      currentJobId: current.id,
      originalJobId: current.id,
      resultPath: current.result_path || undefined,
    };
  }
  return { generationGroupId, generationGroupSize, slots };
}

export function reconcileGenerationReviewSession(
  session: GenerationReviewSession,
  jobs: GenerationJobRecord[],
): GenerationReviewSession {
  const byIndex = groupJobsByStableSlot(jobs, session.generationGroupId);
  let changed = false;
  const slots = session.slots.map(slot => {
    const currentJob = slot.currentJobId ? jobs.find(job => job.id === slot.currentJobId) : undefined;
    if (currentJob) {
      if (slot.resultPath && ['discarded', 'cancelled', 'failed'].includes(currentJob.status)) {
        changed = true;
        return { ...slot, resultPath: undefined };
      }
      return slot;
    }
    const job = byIndex.get(slot.index);
    if (!job || job.id === slot.currentJobId) return slot;
    changed = true;
    return {
      ...slot,
      currentJobId: job.id,
      originalJobId: slot.originalJobId || job.id,
      resultPath: ['discarded', 'cancelled', 'failed'].includes(job.status)
        ? undefined
        : slot.resultPath || job.result_path || undefined,
    };
  });
  return changed ? { ...session, slots } : session;
}

export function mapGenerationRetryToReviewSlot(
  session: GenerationReviewSession,
  originalJob: GenerationJobRecord,
  retryJob: GenerationJobRecord,
): GenerationReviewSession {
  const slotIndex = originalJob.generation_group_index
    || session.slots.find(slot => slot.currentJobId === originalJob.id)?.index;
  if (!slotIndex) return session;
  return {
    ...session,
    slots: session.slots.map(slot => slot.index === slotIndex ? {
      ...slot,
      currentJobId: retryJob.id,
      originalJobId: slot.originalJobId || originalJob.id,
      resultPath: undefined,
      resolution: undefined,
    } : slot),
  };
}

export function resolveGenerationReviewSlot(
  session: GenerationReviewSession,
  job: GenerationJobRecord,
  resolution: NonNullable<GenerationReviewSlot['resolution']>,
  target?: Pick<GenerationReviewSlot, 'targetItemId' | 'targetItemTitle' | 'resultPath'>,
): GenerationReviewSession {
  return {
    ...session,
    slots: session.slots.map(slot => (
      slot.currentJobId === job.id
        || slot.originalJobId === job.id
        || (job.generation_group_id === session.generationGroupId && job.generation_group_index === slot.index)
        ? {
          ...slot,
          resolution,
          targetItemId: target?.targetItemId || slot.targetItemId,
          targetItemTitle: target?.targetItemTitle || slot.targetItemTitle,
          resultPath: ['discarded', 'cancelled', 'failed'].includes(resolution)
            ? undefined
            : slot.resultPath || target?.resultPath || job.result_path || undefined,
        }
        : slot
    )),
  };
}

/**
 * Keep review navigation on the original batch slots, even after a result is
 * accepted, discarded, or replaced by a retry. Missing slots remain visible
 * to callers as empty slots until the next jobs refresh reconciles them.
 */
export function generationReviewSlotNavigation(
  session: GenerationReviewSession,
  currentJobId?: string,
): GenerationReviewSlotNavigation {
  const index = session.slots.findIndex(slot => slot.currentJobId === currentJobId || slot.originalJobId === currentJobId);
  const currentIndex = index >= 0 ? index : 0;
  return {
    slots: session.slots,
    index: currentIndex,
    total: session.slots.length,
    previous: session.slots[currentIndex - 1],
    next: session.slots[currentIndex + 1],
  };
}

export function generationReviewNext(
  jobs: GenerationJobRecord[],
  session: GenerationReviewSession,
  currentJobId?: string,
): GenerationJobRecord | undefined {
  if (!session.slots.length) return undefined;
  const currentSlot = session.slots.findIndex(slot => slot.currentJobId === currentJobId);
  const start = currentSlot >= 0 ? currentSlot + 1 : 0;
  const orderedSlots = session.slots.map((_, index) => session.slots[(start + index) % session.slots.length]);
  for (const slot of orderedSlots) {
    if (slot.resolution) continue;
    const candidate = slot.currentJobId
      ? jobs.find(job => job.id === slot.currentJobId)
      : jobs.find(job => job.generation_group_id === session.generationGroupId && job.generation_group_index === slot.index);
    if (isActionableGenerationResult(candidate)) return candidate;
  }
  return undefined;
}

export function generationReviewSummary(
  jobs: GenerationJobRecord[],
  session: GenerationReviewSession,
  pendingRetryJobIds: string[] = [],
): GenerationReviewSummary {
  const pendingRetryIds = new Set(pendingRetryJobIds);
  let actionable = 0;
  let pendingGeneration = 0;
  let pendingRetry = 0;
  let saved = 0;
  let attached = 0;
  let discarded = 0;
  let failedOrCancelled = 0;
  session.slots.forEach(slot => {
    const job = slot.currentJobId
      ? jobs.find(candidate => candidate.id === slot.currentJobId)
      : jobs.find(candidate => candidate.generation_group_id === session.generationGroupId && candidate.generation_group_index === slot.index);
    if (slot.resolution === 'saved') saved += 1;
    else if (slot.resolution === 'attached') attached += 1;
    else if (slot.resolution === 'discarded') discarded += 1;
    else if (slot.resolution === 'failed' || slot.resolution === 'cancelled') failedOrCancelled += 1;
    else if (isActionableGenerationResult(job)) actionable += 1;
    else if (job && ['queued', 'running'].includes(job.status)) {
      if (pendingRetryIds.has(job.id)) pendingRetry += 1;
      else pendingGeneration += 1;
    } else if (job?.status === 'accepted') saved += 1;
    else if (job?.status === 'discarded') discarded += 1;
    else if (job && ['failed', 'cancelled'].includes(job.status)) failedOrCancelled += 1;
    else if (!job) pendingGeneration += 1;
  });
  const resolved = saved + attached + discarded + failedOrCancelled;
  return {
    total: session.generationGroupSize,
    actionable,
    pendingGeneration,
    pendingRetry,
    saved,
    attached,
    discarded,
    failedOrCancelled,
    resolved,
    complete: actionable === 0 && pendingGeneration === 0 && pendingRetry === 0,
  };
}

/** Keep retry indicators only while a loaded retry is still pending. */
export function retainPendingRetryJobIds(
  pendingRetryJobIds: string[],
  jobs: GenerationJobRecord[],
): string[] {
  const loadedJobs = new Map(jobs.map(job => [job.id, job]));
  return pendingRetryJobIds.filter(jobId => {
    const job = loadedJobs.get(jobId);
    return !job || job.status === 'queued' || job.status === 'running';
  });
}

/**
 * Return the deterministic, non-wrapping navigation set for a generation
 * result. Standalone jobs have no siblings; grouped jobs are ordered by their
 * persisted one-based generation_group_index.
 */
export function generationSiblingNavigation(
  jobs: GenerationJobRecord[],
  current?: GenerationJobRecord,
): GenerationSiblingNavigation {
  if (!current?.generation_group_id) {
    return { siblings: current ? [current] : [], index: current ? 0 : -1, total: current ? 1 : 0 };
  }

  const groupedJobs = jobs.filter(job => job.generation_group_id === current.generation_group_id);
  const indexedJobs = groupJobsByStableSlot(groupedJobs, current.generation_group_id, current.id);
  const siblings = [
    ...indexedJobs.values(),
    ...groupedJobs.filter(job => !job.generation_group_index),
  ]
    .sort((left, right) => {
      const leftIndex = left.generation_group_index ?? Number.MAX_SAFE_INTEGER;
      const rightIndex = right.generation_group_index ?? Number.MAX_SAFE_INTEGER;
      if (leftIndex !== rightIndex) return leftIndex - rightIndex;
      const createdOrder = left.created_at.localeCompare(right.created_at);
      return createdOrder || left.id.localeCompare(right.id);
    });
  const index = siblings.findIndex(job => job.id === current.id);
  if (index < 0) {
    return { siblings: [current], index: 0, total: 1 };
  }
  return {
    siblings,
    index,
    total: siblings.length,
    previous: siblings[index - 1],
    next: siblings[index + 1],
  };
}
