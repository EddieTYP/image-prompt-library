import type { ItemSummary } from '../types';
import ItemCard from './ItemCard';

export default function CardsView({
  items,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
  onAdd,
}: {
  items: ItemSummary[];
  onOpen: (id: string) => void;
  onFavorite: (id: string) => void;
  onEdit: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd: () => void;
}) {
  if (!items.length) {
    return (
      <div className="empty">
        <h2>No matching prompts</h2>
        <p>Try another search, clear filters, or add a new prompt reference.</p>
        <div className="empty-actions">
          <button className="empty-primary" onClick={onAdd}>Add your first prompt</button>
        </div>
      </div>
    );
  }

  return (
    <section className="cards-grid masonry-like">
      {items.map(item => (
        <ItemCard key={item.id} item={item} onOpen={onOpen} onFavorite={onFavorite} onEdit={onEdit} onCopyPrompt={onCopyPrompt} />
      ))}
    </section>
  );
}
