import { useEffect, useState } from 'react';
import { Copy, ExternalLink, Heart, Pencil, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import type { ImageRecord, ItemDetail } from '../types';
import { copyTextToClipboard } from '../utils/clipboard';
import { imageDisplayPath, imageHeroPath, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';
import { PROMPT_LANGUAGE_LABELS, resolvePromptText, type PromptLanguage } from '../utils/prompts';

const LANG_LABELS: Record<string, string> = {
  ...PROMPT_LANGUAGE_LABELS,
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
  t,
  preferredLanguage,
  onClose,
  onCopyPrompt,
  onEdit,
}: {
  id?: string;
  t: Translator;
  preferredLanguage: PromptLanguage;
  onClose: () => void;
  onCopyPrompt: (success: boolean) => void;
  onEdit: (item: ItemDetail) => void;
}) {
  const [item, setItem] = useState<ItemDetail>();
  const [lang, setLang] = useState<string>(preferredLanguage);

  useEffect(() => { setLang(preferredLanguage); }, [preferredLanguage, id]);

  useEffect(() => {
    if (!id) return;
    setItem(undefined);
    api.item(id).then(setItem);
  }, [id]);

  if (!id) return null;

  const prompt = item?.prompts.find(p => p.language === lang) || item?.prompts.find(p => p.language === preferredLanguage) || item?.prompts.find(p => p.language === 'en') || item?.prompts[0];
  const copyText = prompt?.text || resolvePromptText(item?.prompts, preferredLanguage, item?.title || '');
  const uniqueImages = dedupeImages(item?.images || []);
  const primaryImage = selectPrimaryImage(uniqueImages);
  const handleCopyPrompt = async () => {
    const copied = await copyTextToClipboard(copyText);
    onCopyPrompt(copied);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="detail modal polished-modal" onClick={e => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label={t('close')}>
          <X size={20} />
        </button>
        {!item ? (
          <p className="modal-loading">{t('loading')}</p>
        ) : (
          <div className="detail-layout">
            <section className="modal-hero">
              {primaryImage ? (
                <img
                  className="hero-image"
                  src={mediaUrl(imageHeroPath(primaryImage))}
                  alt={item.title}
                />
              ) : (
                <div className="placeholder hero-image">{t('noImage')}</div>
              )}
              {uniqueImages.length > 1 && (
                <div className="rail glass-rail">
                  {uniqueImages.map(img => (
                    <img key={getImageIdentity(img)} src={mediaUrl(imageDisplayPath(img))} alt="" />
                  ))}
                </div>
              )}
            </section>

            <aside className="detail-side">
              <div className="modal-kicker">{item.cluster?.name || t('unclustered')}</div>
              <h2>{item.title}</h2>
              <p className="muted">{item.model || t('defaultModel')} · {item.source_name || t('localReference')}</p>

              <div className="tabs prompt-tabs" aria-label={t('promptLanguage')}>
                {Array.from(new Set([preferredLanguage, 'zh_hant', 'en', 'zh_hans'])).map(l => (
                  <button key={l} className={lang === l ? 'active' : ''} onClick={() => setLang(l)}>
                    {LANG_LABELS[l] || l}
                  </button>
                ))}
              </div>

              <div className="prompt-panel">
                <textarea readOnly value={prompt?.text || ''} aria-label={t('promptText')} />
              </div>

              <div className="actions modal-actions">
                <button onClick={handleCopyPrompt}>
                  <Copy size={16} /> {t('copyPrompt')}
                </button>
                <button onClick={() => api.favorite(item.id).then(setItem)}>
                  <Heart size={16} /> {item.favorite ? t('saved') : t('favorite')}
                </button>
                <button onClick={() => onEdit(item)}>
                  <Pencil size={16} /> {t('edit')}
                </button>
                {item.source_url && (
                  <a href={item.source_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={16} /> {t('source')}
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
