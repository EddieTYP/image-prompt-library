import { useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import { Bell, CheckCircle2, Clock3, ImagePlus, Maximize2, Trash2, X, XCircle } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import type { GenerationJobRecord } from '../types';
import type { Translator } from '../utils/i18n';

function isActive(job: GenerationJobRecord) {
  return job.status === 'queued' || job.status === 'running';
}

function statusIcon(job: GenerationJobRecord) {
  if (isActive(job)) return <Clock3 size={16} />;
  if (job.status === 'succeeded') return <ImagePlus size={16} />;
  if (job.status === 'failed') return <XCircle size={16} />;
  return <CheckCircle2 size={16} />;
}

function statusLabel(job: GenerationJobRecord, isUsedAsGenerationReference = false) {
  if (job.status === 'queued') return 'Queued';
  if (job.status === 'running') return 'Running';
  if (job.status === 'succeeded') return isUsedAsGenerationReference ? 'Used as ref' : 'Ready';
  if (job.status === 'failed') return 'Failed';
  if (job.status === 'accepted') return 'Saved';
  if (job.status === 'discarded') return 'Discarded';
  if (job.status === 'cancelled') return 'Cancelled';
  return job.status;
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

const STALE_RUNNING_JOB_MS = 30 * 60 * 1000;

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
  return job.result_path ? mediaUrl(job.result_path) : '';
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

export default function GenerationQueueDrawer({
  t,
  open,
  onOpen,
  onClose,
  onOpenJob,
}: {
  t: Translator;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  onOpenJob: (job: GenerationJobRecord) => void;
}) {
  const [jobs, setJobs] = useState<GenerationJobRecord[]>([]);
  const [loadError, setLoadError] = useState('');
  const [cancelBusyIds, setCancelBusyIds] = useState<Set<string>>(() => new Set());
  const [retryBusyIds, setRetryBusyIds] = useState<Set<string>>(() => new Set());
  const [markFailedBusyIds, setMarkFailedBusyIds] = useState<Set<string>>(() => new Set());
  const [discardBusyIds, setDiscardBusyIds] = useState<Set<string>>(() => new Set());

  const refresh = async () => {
    try {
      const result = await api.generationJobs({ limit: 100 });
      setJobs(result.jobs);
      setLoadError('');
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Could not load generation queue.');
    }
  };

  useEffect(() => {
    refresh().catch(() => undefined);
    const timer = window.setInterval(() => refresh().catch(() => undefined), 6000);
    return () => window.clearInterval(timer);
  }, []);

  const cancelJob = async (job: GenerationJobRecord) => {
    if (!isActive(job) || cancelBusyIds.has(job.id)) return;
    setCancelBusyIds(current => new Set(current).add(job.id));
    try {
      const updated = await api.cancelGenerationJob(job.id);
      setJobs(current => current.map(candidate => candidate.id === updated.id ? updated : candidate));
      setLoadError('');
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Could not cancel generation job.');
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
      setLoadError(error instanceof Error ? error.message : 'Could not retry generation job.');
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
      setLoadError(error instanceof Error ? error.message : 'Could not mark generation job failed.');
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
      setLoadError(error instanceof Error ? error.message : 'Could not discard generation result.');
    } finally {
      setDiscardBusyIds(current => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  };

  const openJobFromKeyboard = (event: KeyboardEvent<HTMLDivElement>, job: GenerationJobRecord) => {
    if (!canOpenJob(job)) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpenJob(job);
    }
  };

  const counts = useMemo(() => ({
    running: jobs.filter(job => job.status === 'running').length,
    queued: jobs.filter(job => job.status === 'queued').length,
    active: jobs.filter(isActive).length,
    ready: jobs.filter(job => job.status === 'succeeded').length,
    failed: jobs.filter(job => job.status === 'failed').length,
  }), [jobs]);
  const hasSignal = counts.active + counts.ready + counts.failed > 0;

  const sections = [
    { key: 'active', title: 'In progress', jobs: jobs.filter(isActive) },
    { key: 'ready', title: 'Ready for review', jobs: jobs.filter(job => job.status === 'succeeded') },
    { key: 'failed', title: 'Needs attention', jobs: jobs.filter(job => job.status === 'failed') },
    { key: 'recent', title: 'Recent', jobs: jobs.filter(job => ['accepted', 'discarded', 'cancelled'].includes(job.status)).slice(0, 8) },
  ];

  return (
    <>
      <button className={`generation-queue-trigger ${hasSignal ? 'has-signal' : ''}`} onClick={open ? onClose : onOpen} aria-label="Generation work queue">
        <Bell size={18} />
        {counts.active > 0 && <span className="queue-dot active" aria-label="Active generation jobs" />}
        {counts.ready > 0 && <span className="queue-dot ready" aria-label="Generation results ready" />}
        {counts.failed > 0 && <span className="queue-dot failed" aria-label="Failed generation jobs" />}
      </button>
      {open && (
        <aside className="generation-queue-drawer" aria-label="Generation work queue">
          <div className="drawer-head">
            <div>
              <p className="drawer-eyebrow">Work queue</p>
              <h2>Generation queue</h2>
            </div>
            <button className="modal-icon-button" onClick={onClose} aria-label={t('close')}><X size={20} strokeWidth={2.25} /></button>
          </div>
          {loadError && <p className="error">{loadError}</p>}
          <p className="muted queue-summary">{counts.running} running · {counts.queued} queued · {counts.ready} ready</p>
          {sections.map(section => (
            <section className="generation-queue-section" key={section.key}>
              <h3>{section.title}</h3>
              {section.jobs.length === 0 ? <p className="muted">—</p> : section.jobs.map(job => (
                section.key === 'ready' && job.status === 'succeeded' ? (
                  <div
                    key={job.id}
                    className="generation-queue-result generation-history-item status-succeeded"
                    onClick={() => canOpenJob(job) && onOpenJob(job)}
                    onKeyDown={event => openJobFromKeyboard(event, job)}
                    role="button"
                    tabIndex={0}
                    aria-label={`${statusLabel(job, isUsedAsGenerationReference(job, jobs))} generation result, ${jobAspectRatio(job)}, ${jobQuality(job)}, ${jobModel(job)}`}
                  >
                    <span className="generation-history-media">
                      {jobResultUrl(job) ? <img src={jobResultUrl(job)} alt="" /> : <span className="generation-history-placeholder">{statusLabel(job, isUsedAsGenerationReference(job, jobs))}</span>}
                      <span className="generation-queue-preview-actions">
                        <button
                          type="button"
                          className="generation-queue-quick-expand"
                          onClick={event => {
                            event.stopPropagation();
                            if (canOpenJob(job)) onOpenJob(job);
                          }}
                          aria-label="Expand generation result"
                          title="Expand"
                        >
                          <Maximize2 size={15} aria-hidden="true" />
                        </button>
                        {canDiscardTransientResult(job) && (
                          <button
                            type="button"
                            className="generation-queue-quick-discard"
                            onClick={event => {
                              event.stopPropagation();
                              discardJob(job).catch(() => undefined);
                            }}
                            disabled={discardBusyIds.has(job.id)}
                            aria-label="Discard generation result"
                            title="Discard"
                          >
                            <Trash2 size={15} aria-hidden="true" />
                          </button>
                        )}
                      </span>
                    </span>
                    <span className="generation-history-status-grid" aria-hidden="true">
                      <span className="generation-history-cell"><b>Aspect ratio</b><em>{jobAspectRatio(job)}</em></span>
                      <span className="generation-history-cell"><b>Quality</b><em>{jobQuality(job)}</em></span>
                      <span className="generation-history-cell"><b>Model</b><em>{jobModel(job)}</em></span>
                      <span className="generation-history-cell"><b>Status</b><em>{statusLabel(job, isUsedAsGenerationReference(job, jobs))}</em></span>
                    </span>
                  </div>
                ) : (
                  <div
                    key={job.id}
                    className={`generation-queue-row status-${job.status}`}
                    onClick={() => canOpenJob(job) && onOpenJob(job)}
                    onKeyDown={event => openJobFromKeyboard(event, job)}
                    role={canOpenJob(job) ? 'button' : undefined}
                    tabIndex={canOpenJob(job) ? 0 : undefined}
                    aria-disabled={!canOpenJob(job)}
                  >
                    {statusIcon(job)}
                    <span>{job.edited_prompt_text || job.prompt_text}</span>
                    <span className="generation-queue-row-actions">
                      <b>{statusLabel(job, isUsedAsGenerationReference(job, jobs))}</b>
                      {isActive(job) && (
                        <button
                          type="button"
                          className="generation-queue-cancel"
                          onClick={event => {
                            event.stopPropagation();
                            cancelJob(job).catch(() => undefined);
                          }}
                          disabled={cancelBusyIds.has(job.id)}
                        >Cancel</button>
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
                        >Mark failed</button>
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
                        >Retry</button>
                      )}
                      {job.status === 'failed' && retriedByJobId(job) && <em>Retried</em>}
                    </span>
                  </div>
                )
              ))}
            </section>
          ))}
        </aside>
      )}
    </>
  );
}
