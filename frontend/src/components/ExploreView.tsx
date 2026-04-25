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
    <section className="explore-grid">
      {clusters.map((c, cardIndex) => (
        <button
          className={`cluster-card ${cardIndex % 5 === 1 ? 'featured' : ''}`}
          key={c.id}
          onClick={() => onSelect(c)}
        >
          <div className="thumb-strip">
            {c.preview_images.slice(0, 4).map((p, idx) => (
              <img
                key={`${c.id}-${idx}-${p}`}
                src={mediaUrl(p)}
                loading="lazy"
                decoding="async"
                alt=""
              />
            ))}
            {!c.preview_images.length && <span className="gradient" />}
          </div>
          <h3>{c.name}</h3>
          <p>{c.count} prompt{c.count === 1 ? '' : 's'}</p>
        </button>
      ))}
    </section>
  );
}
