import { useEffect, useMemo, useState } from 'react';
import { Bell, CheckCircle2, Clock3, ImagePlus, XCircle } from 'lucide-react';
import { api } from '../api/client';
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

function statusLabel(job: GenerationJobRecord) {
  if (job.status === 'queued') return 'Queued';
  if (job.status === 'running') return 'Running';
  if (job.status === 'succeeded') return 'Ready';
  if (job.status === 'failed') return 'Failed';
  if (job.status === 'accepted') return 'Saved';
  if (job.status === 'discarded') return 'Discarded';
  if (job.status === 'cancelled') return 'Cancelled';
  return job.status;
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

  const refresh = async () => {
    try {
      const result = await api.generationJobs({ limit: 50 });
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
            <button className="modal-icon-button" onClick={onClose} aria-label={t('close')}>×</button>
          </div>
          {loadError && <p className="error">{loadError}</p>}
          <p className="muted queue-summary">{counts.running} running · {counts.queued} queued · {counts.ready} ready</p>
          {sections.map(section => (
            <section className="generation-queue-section" key={section.key}>
              <h3>{section.title}</h3>
              {section.jobs.length === 0 ? <p className="muted">—</p> : section.jobs.map(job => (
                <button
                  type="button"
                  key={job.id}
                  className={`generation-queue-row status-${job.status}`}
                  onClick={() => onOpenJob(job)}
                >
                  {statusIcon(job)}
                  <span>{job.edited_prompt_text || job.prompt_text}</span>
                  <b>{statusLabel(job)}</b>
                </button>
              ))}
            </section>
          ))}
        </aside>
      )}
    </>
  );
}
