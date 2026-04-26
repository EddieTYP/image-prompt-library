import type { MouseEvent } from 'react';
import { Copy, Heart, Pencil } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ItemSummary } from '../types';
import { imageDisplayPath, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';

export default function ItemCard({
  item,
  t,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
}: {
  item: ItemSummary;
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite: (id: string) => void;
  onEdit: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
}) {
  const primaryImage = selectPrimaryImage([item.first_image]);
  const imagePath = imageDisplayPath(primaryImage);
  const imageAspectRatio = primaryImage?.width && primaryImage?.height
    ? `${primaryImage.width} / ${primaryImage.height}`
    : undefined;
  const copyPrompt = (event: MouseEvent) => {
    event.stopPropagation();
    onCopyPrompt(item);
  };
  const favorite = (event: MouseEvent) => {
    event.stopPropagation();
    onFavorite(item.id);
  };
  const edit = (event: MouseEvent) => {
    event.stopPropagation();
    onEdit(item);
  };

  return (
    <article className={`item-card ${item.favorite ? 'is-favorite' : ''}`} style={{ breakInside: 'avoid' }} onClick={() => onOpen(item.id)}>
      {imagePath ? (
        <div className={`card-image-frame ${imageAspectRatio ? 'has-reserved-ratio' : 'natural-ratio'}`} style={{ aspectRatio: imageAspectRatio }}>
          <img
            src={mediaUrl(imagePath)}
            loading="lazy"
            decoding="async"
            width={primaryImage?.width || undefined}
            height={primaryImage?.height || undefined}
            alt={item.title}
          />
        </div>
      ) : <div className="placeholder">{t('noImage')}</div>}
      <div className="card-body">
        <h3>{item.title}</h3>
        <p>{item.cluster?.name || t('unclustered')} · {item.source_name || item.model} {item.favorite && <Heart size={13} fill="currentColor" />}</p>
      </div>
      <div className="card-actions" aria-label={t('itemActions')}>
        <button className="hover-action" onClick={copyPrompt}><Copy size={15} /> {t('copyPrompt')}</button>
        <button className="hover-action" onClick={favorite}><Heart size={15} fill={item.favorite ? 'currentColor' : 'none'} /> {t('favorite')}</button>
        <button className="hover-action" onClick={edit}><Pencil size={15} /> {t('edit')}</button>
      </div>
    </article>
  );
}
