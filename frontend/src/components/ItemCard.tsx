import type { MouseEvent } from 'react';
import { Copy, Heart, Pencil } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ItemSummary } from '../types';

export default function ItemCard({
  item,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
}: {
  item: ItemSummary;
  onOpen: (id: string) => void;
  onFavorite: (id: string) => void;
  onEdit: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
}) {
  const imagePath = item.first_image?.thumb_path || item.first_image?.preview_path || item.first_image?.original_path;
  const imageAspectRatio = item.first_image?.width && item.first_image?.height
    ? `${item.first_image.width} / ${item.first_image.height}`
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
            width={item.first_image?.width || undefined}
            height={item.first_image?.height || undefined}
            alt={item.title}
          />
        </div>
      ) : <div className="placeholder">No image</div>}
      <div className="card-body">
        <h3>{item.title}</h3>
        <p>{item.cluster?.name || 'Unclustered'} · {item.source_name || item.model} {item.favorite && <Heart size={13} fill="currentColor" />}</p>
      </div>
      <div className="card-actions" aria-label="Item actions">
        <button className="hover-action" onClick={copyPrompt}><Copy size={15} /> Copy prompt</button>
        <button className="hover-action" onClick={favorite}><Heart size={15} fill={item.favorite ? 'currentColor' : 'none'} /> Favorite</button>
        <button className="hover-action" onClick={edit}><Pencil size={15} /> Edit</button>
      </div>
    </article>
  );
}
