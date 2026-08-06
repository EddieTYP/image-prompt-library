import type { ItemSortMode, ItemSummary } from '../types';
import type { Translator } from '../utils/i18n';
import ItemCard from './ItemCard';
import ScopeHeader from './ScopeHeader';

export default function CardsView({
  items,
  loading = false,
  emptyMode,
  t,
  onOpen,
  onFavorite,
  onEdit,
  editingItemId,
  onToggleSelection,
  selectedIds,
  onCopyPrompt,
  onAdd,
  onOpenConfig,
  total,
  sort,
  onSort,
  clusterName,
  hasActiveSearch = false,
  onClearCluster,
}: {
  items: ItemSummary[];
  loading?: boolean;
  emptyMode?: 'first-run' | 'no-results';
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  editingItemId?: string;
  onToggleSelection?: (id: string) => void;
  selectedIds?: Set<string>;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd?: () => void;
  onOpenConfig?: () => void;
  total: number;
  sort: ItemSortMode;
  onSort: (sort: ItemSortMode) => void;
  clusterName?: string;
  hasActiveSearch?: boolean;
  onClearCluster: () => void;
}) {
  const showActions = Boolean(onFavorite && onEdit) && !onToggleSelection;
  if (!items.length && loading) {
    return (
      <>
        <ScopeHeader
          t={t}
          title={clusterName || t(hasActiveSearch ? 'searchResults' : 'allReferences')}
          count={0}
          countLabel={t('referencesShown')}
          sort={sort}
          onSort={onSort}
        />
        <div className="content-loading-state" role="status" aria-label={t('loading')}>
          <span /><span /><span />
        </div>
      </>
    );
  }
  if (!items.length && emptyMode === 'first-run') {
    return (
      <>
        <ScopeHeader
          t={t}
          title={t(hasActiveSearch ? 'searchResults' : 'allReferences')}
          count={0}
          countLabel={t('referencesShown')}
          sort={sort}
          onSort={onSort}
        />
        <div className="empty first-run-empty">
          <p className="empty-eyebrow">{t('firstRunLocalInstall')}</p>
          <h2>{t('firstRunEmptyTitle')}</h2>
          <p>{t('firstRunEmptyHelp')}</p>
          <div className="empty-actions">
            {onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
            {onOpenConfig && <button className="secondary" onClick={onOpenConfig}>{t('firstRunOpenConfig')}</button>}
          </div>
          <div className="first-run-command">
            <span>{t('firstRunSampleHelp')}</span>
            <code>{t('firstRunSampleCommand')}</code>
          </div>
          <p className="first-run-generation-hint">{t('firstRunGenerationHelp')}</p>
        </div>
      </>
    );
  }

  if (!items.length) {
    return (
      <>
        <ScopeHeader
          t={t}
          title={clusterName || t(hasActiveSearch ? 'searchResults' : 'allReferences')}
          count={total}
          countLabel={t('referencesShown')}
          sort={sort}
          onSort={onSort}
          backLabel={clusterName ? t(hasActiveSearch ? 'searchResults' : 'allReferences') : undefined}
          onBack={clusterName ? onClearCluster : undefined}
        />
        <div className="empty">
          <h2>{t('noMatchingPrompts')}</h2>
          <p>{t('noMatchingPromptsHelp')}</p>
          <div className="empty-actions">
            {onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
          </div>
        </div>
      </>
    );
  }

  const renderCard = (item: ItemSummary) => (
    <ItemCard key={item.id} t={t} item={item} onOpen={onOpen} onFavorite={onFavorite} onEdit={onEdit} editBusy={editingItemId === item.id} onToggleSelection={onToggleSelection} isSelecting={Boolean(onToggleSelection)} isSelected={Boolean(selectedIds?.has(item.id))} onCopyPrompt={onCopyPrompt} showActions={showActions} />
  );

  return (
    <>
      <ScopeHeader
        t={t}
        title={clusterName || t(hasActiveSearch ? 'searchResults' : 'allReferences')}
        count={total}
        countLabel={t('referencesShown')}
        sort={sort}
        onSort={onSort}
        backLabel={clusterName ? t(hasActiveSearch ? 'searchResults' : 'allReferences') : undefined}
        onBack={clusterName ? onClearCluster : undefined}
      />
      <section className={`cards-grid masonry-like responsive-cards-grid${onToggleSelection ? ' is-selecting' : ''}${clusterName && items.length <= 8 ? ` is-sparse sparse-count-${items.length}` : ''}`}>
        {items.map(renderCard)}
      </section>
    </>
  );
}
