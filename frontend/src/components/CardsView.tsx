import type { ItemSummary } from '../types';
import ItemCard from './ItemCard';

export default function CardsView({
  items,
  onOpen,
  onFavorite,
  onEdit,
}: {
  items: ItemSummary[];
  onOpen: (id: string) => void;
  onFavorite: (id: string) => void;
  onEdit: (item: ItemSummary) => void;
}) {
  if (!items.length) {
    return (
      <div className="empty">
        <h2>No matching prompts</h2>
        <p>Try another search or cluster.</p>
      </div>
    );
  }

  return (
    <section className="cards-grid masonry-like">
      {items.map(item => (
        <ItemCard key={item.id} item={item} onOpen={onOpen} onFavorite={onFavorite} onEdit={onEdit} />
      ))}
    </section>
  );
}
