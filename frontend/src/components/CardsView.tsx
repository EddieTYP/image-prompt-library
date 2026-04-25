import type { ItemSummary } from '../types';
import ItemCard from './ItemCard';

export default function CardsView({
  items,
  onOpen,
}: {
  items: ItemSummary[];
  onOpen: (id: string) => void;
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
        <ItemCard key={item.id} item={item} onOpen={onOpen} />
      ))}
    </section>
  );
}
