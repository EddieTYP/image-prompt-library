import type { GenerationJobSetRecord, GenerationProviderQueueState } from '../types';

export function generationSetProgressText(set: GenerationJobSetRecord) {
  const parts = [`${set.completed} of ${set.total} finished`];
  if (set.running) parts.push(`${set.running} running`);
  if (set.queued) parts.push(`${set.queued} queued`);
  if (set.succeeded) parts.push(`${set.succeeded} ready`);
  if (set.failed) parts.push(`${set.failed} failed`);
  if (set.cancelled) parts.push(`${set.cancelled} cancelled`);
  return parts.join(' · ');
}

export function providerPauseSeconds(state: GenerationProviderQueueState, currentTime = Date.now()) {
  if (!state.paused || !state.paused_until) return 0;
  const pausedUntil = Date.parse(state.paused_until);
  if (!Number.isFinite(pausedUntil)) return Math.max(0, state.retry_after_seconds || 0);
  return Math.max(0, Math.ceil((pausedUntil - currentTime) / 1000));
}
