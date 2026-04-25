import { mediaUrl } from '../api/client';
import type { ClusterRecord } from '../types';

export default function ExploreView({
  clusters,
  onSelect,
}: {
  clusters: ClusterRecord[];
  onSelect: (c: ClusterRecord) => void;
}) {
  if (!clusters.length) {
    return (
      <div className="empty">
        <h2>No clusters yet</h2>
        <p>Import OpenNana or add your first prompt to start exploring.</p>
      </div>
    );
  }

  return (
    <section className="cluster-orbit" aria-label="Prompt clusters orbit view">
      {clusters.map((c, cardIndex) => {
        const previews = c.preview_images.slice(0, 5);
        return (
          <button className="orbit-cluster" key={c.id} onClick={() => onSelect(c)}>
            <div className="orbit-stage" aria-hidden="true">
              {previews.map((p, idx) => (
                <img
                  key={`${c.id}-${idx}-${p}`}
                  className={`orbit-preview orbit-preview-${idx + 1}`}
                  src={mediaUrl(p)}
                  loading="lazy"
                  decoding="async"
                  alt=""
                />
              ))}
              {!previews.length && <span className="orbit-preview orbit-fallback" />}
              <span className="orbit-ring orbit-ring-one" />
              <span className="orbit-ring orbit-ring-two" />
            </div>
            <span className="cluster-name">{c.name}</span>
            <span className="cluster-count">
              {c.count} reference{c.count === 1 ? '' : 's'}
            </span>
            <span className="cluster-action">Open collection</span>
          </button>
        );
      })}
    </section>
  );
}
