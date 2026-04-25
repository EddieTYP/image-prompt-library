import { useEffect, useState } from 'react';
import { Copy, ExternalLink, Heart, Pencil, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import type { ImageRecord, ItemDetail } from '../types';
import { copyTextToClipboard } from '../utils/clipboard';
import { PROMPT_LANGUAGE_LABELS, resolvePromptText, type PromptLanguage } from '../utils/prompts';

const LANG_LABELS: Record<string, string> = {
  ...PROMPT_LANGUAGE_LABELS,
  original: 'Original',
};

function getImageIdentity(image: ImageRecord) {
  return image.thumb_path || image.preview_path || image.original_path || image.id;
}

function dedupeImages(images: ImageRecord[]) {
  const seenImageKeys = new Set<string>();
  return images.filter(image => {
    const key = getImageIdentity(image);
    if (seenImageKeys.has(key)) return false;
    seenImageKeys.add(key);
    return true;
  });
}

export default function ItemDetailModal({
  id,
  preferredLanguage,
  onClose,
  onEdit,
}: {
  id?: string;
  preferredLanguage: PromptLanguage;
  onClose: () => void;
  onEdit: (item: ItemDetail) => void;
}) {
  const [item, setItem] = useState<ItemDetail>();
  const [lang, setLang] = useState<string>(preferredLanguage);
  const [copyFeedback, setCopyFeedback] = useState<string>();

  useEffect(() => { setLang(preferredLanguage); }, [preferredLanguage, id]);

  useEffect(() => {
    if (!id) return;
    setItem(undefined);
    setCopyFeedback(undefined);
    api.item(id).then(setItem);
  }, [id]);

  if (!id) return null;

  const prompt = item?.prompts.find(p => p.language === lang) || item?.prompts.find(p => p.language === preferredLanguage) || item?.prompts.find(p => p.language === 'en') || item?.prompts[0];
  const copyText = prompt?.text || resolvePromptText(item?.prompts, preferredLanguage, item?.title || '');
  const uniqueImages = dedupeImages(item?.images || []);
  const primaryImage = uniqueImages[0];
  const handleCopyPrompt = async () => {
    const copied = await copyTextToClipboard(copyText);
    setCopyFeedback(copied ? 'Copied prompt' : 'Copy failed');
    window.setTimeout(() => setCopyFeedback(undefined), 1800);
  };

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
              {uniqueImages.length > 1 && (
                <div className="rail glass-rail">
                  {uniqueImages.map(img => (
                    <img key={getImageIdentity(img)} src={mediaUrl(img.thumb_path || img.original_path)} alt="" />
                  ))}
                </div>
              )}
            </section>

            <aside className="detail-side">
              <div className="modal-kicker">{item.cluster?.name || 'Unsorted collection'}</div>
              <h2>{item.title}</h2>
              <p className="muted">{item.model || 'ChatGPT Image'} · {item.source_name || 'Local reference'}</p>

              <div className="tabs prompt-tabs" aria-label="Prompt language">
                {Array.from(new Set([preferredLanguage, 'zh_hant', 'en', 'original', 'zh_hans'])).map(l => (
                  <button key={l} className={lang === l ? 'active' : ''} onClick={() => setLang(l)}>
                    {LANG_LABELS[l] || l}
                  </button>
                ))}
              </div>

              <div className="prompt-panel">
                <textarea readOnly value={prompt?.text || ''} aria-label="Prompt text" />
              </div>

              <div className="actions modal-actions">
                <button onClick={handleCopyPrompt}>
                  <Copy size={16} /> {copyFeedback || 'Copy prompt'}
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
