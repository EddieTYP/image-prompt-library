import type { ItemSummary } from '../types';
import type { Translator } from '../utils/i18n';
import ItemCard from './ItemCard';

export default function CardsView({
  items,
  t,
  onOpen,
  onFavorite,
  onEdit,
  onToggleSelection,
  selectedIds,
  onCopyPrompt,
  onAdd,
}: {
  items: ItemSummary[];
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  onToggleSelection?: (id: string) => void;
  selectedIds?: Set<string>;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd?: () => void;
}) {
  const showActions = Boolean(onFavorite && onEdit) && !onToggleSelection;
  if (!items.length) {
    return (
      <div className="empty">
        <h2>{t('noMatchingPrompts')}</h2>
        <p>{t('noMatchingPromptsHelp')}</p>
        <div className="empty-actions">
          {onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
        </div>
      </div>
    );
  }

  const leftColumnItems = items.filter((_, index) => index % 2 === 0);
  const rightColumnItems = items.filter((_, index) => index % 2 === 1);
  const renderCard = (item: ItemSummary) => (
    <ItemCard key={item.id} t={t} item={item} onOpen={onOpen} onFavorite={onFavorite} onEdit={onEdit} onToggleSelection={onToggleSelection} isSelecting={Boolean(onToggleSelection)} isSelected={Boolean(selectedIds?.has(item.id))} onCopyPrompt={onCopyPrompt} showActions={showActions} />
  );

  return (
    <>
      <section className={`cards-grid masonry-like desktop-cards-grid${onToggleSelection ? ' is-selecting' : ''}`}>
        {items.map(renderCard)}
      </section>
      <section className={`mobile-masonry-columns${onToggleSelection ? ' is-selecting' : ''}`}>
        <div className="mobile-masonry-column">
          {leftColumnItems.map(renderCard)}
        </div>
        <div className="mobile-masonry-column">
          {rightColumnItems.map(renderCard)}
        </div>
      </section>
    </>
  );
}
