import type { MouseEvent } from 'react';
import { Copy, Download, Heart, Pencil } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ItemSummary } from '../types';
import { downloadFileName, imageDisplayPath, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';

export default function ItemCard({
  item,
  t,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
  showActions = true,
}: {
  item: ItemSummary;
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  showActions?: boolean;
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
    onFavorite?.(item.id);
  };
  const edit = (event: MouseEvent) => {
    event.stopPropagation();
    onEdit?.(item);
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
      </div>
      <div className="card-actions" aria-label={t('itemActions')}>
        <button className="hover-action" onClick={copyPrompt} aria-label={t('copyPrompt')} title={t('copyPrompt')}><Copy size={15} /></button>
        {primaryImage && imagePath && <a className="hover-action" href={mediaUrl(primaryImage.original_path || imagePath)} download={downloadFileName(item.title, primaryImage?.original_path || imagePath)} onClick={event => event.stopPropagation()} aria-label="Download" title="Download"><Download size={15} /></a>}
        {showActions && onFavorite && <button className="hover-action" onClick={favorite} aria-label={item.favorite ? t('saved') : t('favorite')} title={item.favorite ? t('saved') : t('favorite')}><Heart size={15} fill={item.favorite ? 'currentColor' : 'none'} /></button>}
        {showActions && onEdit && <button className="hover-action" onClick={edit} aria-label={t('edit')} title={t('edit')}><Pencil size={15} /></button>}
      </div>
    </article>
  );
}
