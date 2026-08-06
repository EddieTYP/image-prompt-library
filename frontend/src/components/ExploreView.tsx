import { useEffect, useMemo, useRef, useState } from 'react';
import { mediaUrl } from '../api/client';
import type { ClusterRecord, ImageRecord, ItemSortMode, ItemSummary } from '../types';
import type { Translator } from '../utils/i18n';
import ItemCard from './ItemCard';
import ScopeHeader from './ScopeHeader';

const EXPLORE_PAGE_SIZE = 48;

type PreviewEntry = {
  image: ImageRecord;
  item: ItemSummary;
};

function previewEntries(items: ItemSummary[]) {
  const byItemId = new Map<string, PreviewEntry>();
  const byPath = new Map<string, PreviewEntry | null>();
  for (const item of items) {
    const image = item.first_image;
    if (!image) continue;
    const entry = { image, item };
    byItemId.set(item.id, entry);
    for (const path of [image.thumb_path, image.preview_path, image.original_path]) {
      if (!path) continue;
      const existing = byPath.get(path);
      if (!byPath.has(path)) byPath.set(path, entry);
      else if (!existing || existing.item.id !== item.id) byPath.set(path, null);
    }
  }
  return { byItemId, byPath };
}

export default function ExploreView({
  t,
  clusters,
  items,
  total,
  hasActiveSearch,
  searchQuery,
  loading,
  sort,
  onSort,
  onOpenCollection,
  onOpen,
  onCopyPrompt,
  onAdd,
}: {
  t: Translator;
  clusters: ClusterRecord[];
  items: ItemSummary[];
  total: number;
  hasActiveSearch: boolean;
  searchQuery: string;
  loading: boolean;
  sort: ItemSortMode;
  onSort: (sort: ItemSortMode) => void;
  onOpenCollection: (cluster: ClusterRecord) => void;
  onOpen: (id: string) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd?: () => void;
}) {
  const [visibleCount, setVisibleCount] = useState(EXPLORE_PAGE_SIZE);
  const loadMoreRef = useRef<HTMLButtonElement | null>(null);
  const nonEmptyClusters = useMemo(() => clusters.filter(cluster => cluster.count > 0), [clusters]);
  const previewMetadata = useMemo(() => previewEntries(items), [items]);
  const visibleItems = useMemo(() => items.slice(0, visibleCount), [items, visibleCount]);
  const hasMore = hasActiveSearch && visibleCount < items.length;

  useEffect(() => {
    setVisibleCount(EXPLORE_PAGE_SIZE);
  }, [hasActiveSearch, searchQuery, items]);

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !hasMore || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some(entry => entry.isIntersecting)) {
        setVisibleCount(count => Math.min(items.length, count + EXPLORE_PAGE_SIZE));
      }
    }, { rootMargin: '480px 0px' });
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMore, items.length, visibleCount]);

  if (loading && !items.length) {
    return (
      <section className={hasActiveSearch ? 'explore-feed' : 'explore-directory'} aria-label={hasActiveSearch ? t('searchResults') : t('collections')} aria-busy="true">
        <ScopeHeader
          t={t}
          title={hasActiveSearch ? t('searchResults') : t('collections')}
          count={0}
          countLabel={hasActiveSearch ? t('referencesShown') : t('collections')}
          sort={hasActiveSearch ? sort : undefined}
          onSort={hasActiveSearch ? onSort : undefined}
        />
        <div className="content-loading-state" role="status" aria-label={t('loading')}>
          <span /><span /><span />
        </div>
      </section>
    );
  }

  if (!hasActiveSearch && !nonEmptyClusters.length) {
    const libraryIsEmpty = total === 0;
    return (
      <section className="explore-directory" aria-label={t('collections')} aria-busy={loading}>
        <ScopeHeader t={t} title={t('collections')} count={0} countLabel={t('collections')} />
        <div className="empty">
          <h2>{t(libraryIsEmpty ? 'libraryEmptyTitle' : 'noCollectionsFound')}</h2>
          <p>{libraryIsEmpty ? t('libraryEmptyHelp') : `${total} ${t('referencesShown')}`}</p>
          <div className="empty-actions">
            {libraryIsEmpty && onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
          </div>
        </div>
      </section>
    );
  }

  if (hasActiveSearch) {
    return (
      <section className="explore-feed" aria-label={t('searchResults')} aria-busy={loading}>
        <ScopeHeader
          t={t}
          title={t('searchResults')}
          count={total}
          countLabel={t('referencesShown')}
          sort={sort}
          onSort={onSort}
        />

        {!items.length ? (
          <div className="empty explore-empty">
            <h2>{t('noMatchingPrompts')}</h2>
            <p>{t('noMatchingPromptsHelp')}</p>
          </div>
        ) : (
          <>
            <div className="explore-masonry">
              {visibleItems.map(item => (
                <ItemCard
                  key={item.id}
                  t={t}
                  item={item}
                  onOpen={onOpen}
                  onCopyPrompt={onCopyPrompt}
                  showActions={false}
                />
              ))}
            </div>
            {hasMore && (
              <button
                ref={loadMoreRef}
                type="button"
                className="explore-load-more"
                onClick={() => setVisibleCount(count => Math.min(items.length, count + EXPLORE_PAGE_SIZE))}
              >
                {t('more')}
              </button>
            )}
          </>
        )}
      </section>
    );
  }

  return (
    <section className="explore-directory" aria-label={t('collections')} aria-busy={loading}>
      <ScopeHeader
        t={t}
        title={t('collections')}
        count={nonEmptyClusters.length}
        countLabel={t('collections')}
      />
      <div className="explore-collection-grid">
        {nonEmptyClusters.map(cluster => {
          const previews = cluster.preview_images.slice(0, 3);
          return (
            <article key={cluster.id} className="explore-collection-card">
              <button
                type="button"
                className="explore-collection-heading"
                onClick={() => onOpenCollection(cluster)}
                aria-label={`${cluster.name}, ${cluster.count} ${t('referencesShown')}`}
              >
                <strong>{cluster.name}</strong>
                <span>{cluster.count} {t('referencesShown')}</span>
              </button>
              <div className={`explore-collection-previews preview-count-${previews.length}`}>
                {previews.length ? previews.map((path, index) => {
                  const previewItemId = cluster.preview_item_ids?.[index];
                  const entry = (previewItemId && previewMetadata.byItemId.get(previewItemId))
                    || previewMetadata.byPath.get(path)
                    || undefined;
                  const openItemId = previewItemId || entry?.item.id;
                  const image = entry?.image;
                  const previewStyle = { flexGrow: image?.width && image.height ? image.width / image.height : 1 };
                  const previewImage = (
                    <img
                      src={mediaUrl(path)}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      width={image?.width || undefined}
                      height={image?.height || undefined}
                      onLoad={event => {
                        if (image?.width && image.height) return;
                        const { naturalWidth, naturalHeight } = event.currentTarget;
                        if (naturalWidth && naturalHeight && event.currentTarget.parentElement) {
                          event.currentTarget.parentElement.style.flexGrow = String(naturalWidth / naturalHeight);
                        }
                      }}
                    />
                  );
                  return openItemId ? (
                    <button
                      type="button"
                      className="explore-collection-preview"
                      key={`${cluster.id}-${openItemId}-${index}`}
                      style={previewStyle}
                      onClick={() => onOpen(openItemId)}
                      aria-label={`${t('showImage')}: ${entry?.item.title || cluster.name}`}
                      data-card-id={openItemId}
                    >
                      {previewImage}
                    </button>
                  ) : (
                    <span
                      className="explore-collection-preview"
                      key={`${cluster.id}-${path}-${index}`}
                      style={previewStyle}
                      aria-hidden="true"
                    >
                      {previewImage}
                    </span>
                  );
                }) : <span className="explore-collection-placeholder">{t('noImage')}</span>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
