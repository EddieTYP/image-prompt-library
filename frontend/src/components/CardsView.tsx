import type { ItemSummary } from '../types';
import type { Translator } from '../utils/i18n';
import ItemCard from './ItemCard';

export default function CardsView({
  items,
  t,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
  onAdd,
}: {
  items: ItemSummary[];
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite: (id: string) => void;
  onEdit: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd: () => void;
}) {
  if (!items.length) {
    return (
      <div className="empty">
        <h2>{t('noMatchingPrompts')}</h2>
        <p>{t('noMatchingPromptsHelp')}</p>
        <div className="empty-actions">
          <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>
        </div>
      </div>
    );
  }

  return (
    <section className="cards-grid masonry-like">
      {items.map(item => (
        <ItemCard key={item.id} t={t} item={item} onOpen={onOpen} onFavorite={onFavorite} onEdit={onEdit} onCopyPrompt={onCopyPrompt} />
      ))}
    </section>
  );
}
