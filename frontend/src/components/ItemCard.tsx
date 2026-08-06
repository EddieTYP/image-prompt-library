import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, MouseEvent } from 'react';
import { Check, Copy, Download, Heart, LoaderCircle, MoreHorizontal, Pencil } from 'lucide-react';
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
  editBusy = false,
  onToggleSelection,
  onCopyPrompt,
  showActions = true,
  isSelecting = false,
  isSelected = false,
}: {
  item: ItemSummary;
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  editBusy?: boolean;
  onToggleSelection?: (id: string) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  showActions?: boolean;
  isSelecting?: boolean;
  isSelected?: boolean;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const moreShellRef = useRef<HTMLSpanElement | null>(null);
  const moreButtonRef = useRef<HTMLButtonElement | null>(null);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);
  const primaryImage = selectPrimaryImage([item.first_image]);
  const imagePath = imageDisplayPath(primaryImage);
  const imageAspectRatio = primaryImage?.width && primaryImage?.height
    ? `${primaryImage.width} / ${primaryImage.height}`
    : undefined;
  const hasTemplateTag = item.tags.some(tag => tag.name === 'template');
  const downloadLabel = t('download') === 'download' ? 'Download' : t('download');
  const moreActionsLabel = t('moreActions') === 'moreActions' ? 'More actions' : t('moreActions');
  const favoriteLabel = item.favorite ? t('unfavorite') : t('favorite');
  const selectLabel = t('select') === 'select' ? 'Select' : t('select');
  const deselectLabel = t('deselect') === 'deselect' ? 'Deselect' : t('deselect');
  const hasDownload = Boolean(primaryImage && imagePath);
  const hasMoreActions = hasDownload || Boolean(showActions && (onFavorite || onEdit));

  useEffect(() => {
    if (!moreOpen) return;
    const frame = window.requestAnimationFrame(() => {
      moreMenuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    });
    const closeOutside = (event: PointerEvent) => {
      if (!moreShellRef.current?.contains(event.target as Node)) setMoreOpen(false);
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      setMoreOpen(false);
      moreButtonRef.current?.focus();
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [moreOpen]);

  useEffect(() => {
    setMoreOpen(false);
  }, [isSelecting, item.id]);

  const copyPrompt = (event: MouseEvent) => {
    event.stopPropagation();
    onCopyPrompt(item);
  };
  const favorite = (event: MouseEvent) => {
    event.stopPropagation();
    setMoreOpen(false);
    onFavorite?.(item.id);
  };
  const edit = (event: MouseEvent) => {
    event.stopPropagation();
    setMoreOpen(false);
    onEdit?.(item);
  };
  const download = (event: MouseEvent) => {
    event.stopPropagation();
    setMoreOpen(false);
  };
  const toggleMore = (event: MouseEvent) => {
    event.stopPropagation();
    setMoreOpen(open => !open);
  };
  const moveMenuFocus = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Tab') {
      setMoreOpen(false);
      return;
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const menuItems = Array.from(moreMenuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') || []);
    if (!menuItems.length) return;
    event.preventDefault();
    const currentIndex = Math.max(0, menuItems.indexOf(document.activeElement as HTMLElement));
    const nextIndex = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? menuItems.length - 1
        : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + menuItems.length) % menuItems.length;
    menuItems[nextIndex]?.focus();
  };
  const toggleSelection = (event?: MouseEvent) => {
    event?.stopPropagation();
    onToggleSelection?.(item.id);
  };
  const activateCard = () => {
    if (isSelecting) {
      onToggleSelection?.(item.id);
      return;
    }
    onOpen(item.id);
  };
  return (
    <article
      className={`item-card ${item.favorite ? 'is-favorite' : ''} ${isSelecting ? 'is-selecting' : ''} ${isSelected ? 'is-selected' : ''}`}
      style={{ breakInside: 'avoid' }}
    >
      <button
        type="button"
        className="card-open-hit"
        onClick={activateCard}
        data-card-id={item.id}
        tabIndex={isSelecting ? -1 : undefined}
        aria-hidden={isSelecting || undefined}
        aria-label={isSelecting ? undefined : item.title}
      />
      <div className="card-media">
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
        {hasTemplateTag && <span className="card-template-badge" aria-label={t('template')}>{t('template')}</span>}
        {isSelecting && (
          <button className="card-select-action" type="button" onClick={toggleSelection} aria-label={`${isSelected ? deselectLabel : selectLabel} ${item.title}`} aria-pressed={isSelected}>
            <span className="selection-check">{isSelected && <Check size={15} />}</span>
          </button>
        )}
        {!isSelecting && <div className={`card-actions${moreOpen ? ' is-menu-open' : ''}`} role="group" aria-label={t('itemActions')}>
          <button className="hover-action card-action-copy" onClick={copyPrompt} aria-label={t('copyPrompt')} title={t('copyPrompt')}><Copy size={15} /></button>
          {hasDownload && <a className="hover-action card-action-secondary" href={mediaUrl(primaryImage!.original_path || imagePath!)} download={downloadFileName(item.title, primaryImage!.original_path || imagePath!)} onClick={download} aria-label={downloadLabel} title={downloadLabel}><Download size={15} /></a>}
          {showActions && onFavorite && <button className="hover-action card-action-secondary" onClick={favorite} aria-label={favoriteLabel} title={favoriteLabel}><Heart size={15} fill={item.favorite ? 'currentColor' : 'none'} /></button>}
          {showActions && onEdit && <button className="hover-action card-action-secondary" onClick={edit} aria-label={t('edit')} title={t('edit')} disabled={editBusy} aria-busy={editBusy}>{editBusy ? <LoaderCircle className="spin" size={15} /> : <Pencil size={15} />}</button>}
          {hasMoreActions && (
            <span className="card-more-shell" ref={moreShellRef}>
              <button ref={moreButtonRef} className="hover-action card-action-more" type="button" onClick={toggleMore} aria-label={moreActionsLabel} title={moreActionsLabel} aria-haspopup="menu" aria-expanded={moreOpen}>
                <MoreHorizontal size={17} />
              </button>
              {moreOpen && (
                <div ref={moreMenuRef} className="card-action-menu" role="menu" aria-label={moreActionsLabel} onKeyDown={moveMenuFocus}>
                  {hasDownload && <a className="card-action-menu-item" role="menuitem" tabIndex={-1} href={mediaUrl(primaryImage!.original_path || imagePath!)} download={downloadFileName(item.title, primaryImage!.original_path || imagePath!)} onClick={download}><Download size={16} /><span>{downloadLabel}</span></a>}
                  {showActions && onFavorite && <button className="card-action-menu-item" role="menuitem" tabIndex={-1} type="button" onClick={favorite}><Heart size={16} fill={item.favorite ? 'currentColor' : 'none'} /><span>{favoriteLabel}</span></button>}
                  {showActions && onEdit && <button className="card-action-menu-item" role="menuitem" tabIndex={-1} type="button" onClick={edit} disabled={editBusy} aria-busy={editBusy}>{editBusy ? <LoaderCircle className="spin" size={16} /> : <Pencil size={16} />}<span>{t('edit')}</span></button>}
                </div>
              )}
            </span>
          )}
        </div>}
      </div>
      <div className="card-body">
        <h3>{item.title}</h3>
      </div>
      {item.favorite && !isSelecting && (
        <span className="card-favorite-indicator" aria-label={t('saved')}>
          <Heart size={13} fill="currentColor" />
        </span>
      )}
    </article>
  );
}
