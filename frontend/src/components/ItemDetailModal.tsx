import { useEffect, useState } from 'react';
import { Copy, ExternalLink, Heart, Pencil, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import type { ItemDetail } from '../types';

const LANG_LABELS: Record<string, string> = {
  zh_hant: '繁體中文',
  en: 'English',
  original: 'Original',
  zh_hans: '簡體',
};

export default function ItemDetailModal({
  id,
  onClose,
  onEdit,
}: {
  id?: string;
  onClose: () => void;
  onEdit: (item: ItemDetail) => void;
}) {
  const [item, setItem] = useState<ItemDetail>();
  const [lang, setLang] = useState('zh_hant');

  useEffect(() => {
    if (!id) return;
    setItem(undefined);
    api.item(id).then(setItem);
  }, [id]);

  if (!id) return null;

  const prompt = item?.prompts.find(p => p.language === lang) || item?.prompts[0];
  const primaryImage = item?.images[0];

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="detail modal polished-modal" onClick={e => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">
          <X size={20} />
        </button>
        {!item ? (
          <p className="modal-loading">Loading…</p>
        ) : (
          <div className="detail-layout">
            <section className="modal-hero">
              {primaryImage ? (
                <img
                  className="hero-image"
                  src={mediaUrl(primaryImage.preview_path || primaryImage.original_path)}
                  alt={item.title}
                />
              ) : (
                <div className="placeholder hero-image">No image</div>
              )}
              {item.images.length > 1 && (
                <div className="rail glass-rail">
                  {item.images.map(img => (
                    <img key={img.id} src={mediaUrl(img.thumb_path || img.original_path)} alt="" />
                  ))}
                </div>
              )}
            </section>

            <aside className="detail-side">
              <div className="modal-kicker">{item.cluster?.name || 'Unsorted collection'}</div>
              <h2>{item.title}</h2>
              <p className="muted">{item.model || 'ChatGPT Image'} · {item.source_name || 'Local reference'}</p>

              <div className="tabs prompt-tabs" aria-label="Prompt language">
                {['zh_hant', 'en', 'original', 'zh_hans'].map(l => (
                  <button key={l} className={lang === l ? 'active' : ''} onClick={() => setLang(l)}>
                    {LANG_LABELS[l] || l}
                  </button>
                ))}
              </div>

              <div className="prompt-panel">
                <textarea readOnly value={prompt?.text || ''} aria-label="Prompt text" />
              </div>

              <div className="actions modal-actions">
                <button onClick={() => navigator.clipboard?.writeText(prompt?.text || '')}>
                  <Copy size={16} /> Copy prompt
                </button>
                <button onClick={() => api.favorite(item.id).then(setItem)}>
                  <Heart size={16} /> {item.favorite ? 'Saved' : 'Favorite'}
                </button>
                <button onClick={() => onEdit(item)}>
                  <Pencil size={16} /> Edit
                </button>
                {item.source_url && (
                  <a href={item.source_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={16} /> Source
                  </a>
                )}
              </div>

              <div className="tags detail-tags">
                {item.tags.map(t => <span key={t.id}>#{t.name}</span>)}
              </div>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
