import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ClusterRecord, ImageRecord, ItemSummary } from '../types';
import type { Translator } from '../utils/i18n';
import ItemCard from './ItemCard';

const EXPLORE_PAGE_SIZE = 48;

function imageMetadata(items: ItemSummary[]) {
  const images = new Map<string, ImageRecord>();
  for (const item of items) {
    const image = item.first_image;
    if (!image) continue;
    for (const path of [image.thumb_path, image.preview_path, image.original_path]) {
      if (path) images.set(path, image);
    }
  }
  return images;
}

export default function ExploreView({
  t,
  clusters,
  items,
  total,
  focusedClusterId,
  hasActiveSearch,
  searchQuery,
  loading,
  onFocusCluster,
  onClearCluster,
  onOpen,
  onCopyPrompt,
  onAdd,
}: {
  t: Translator;
  clusters: ClusterRecord[];
  items: ItemSummary[];
  total: number;
  focusedClusterId?: string;
  hasActiveSearch: boolean;
  searchQuery: string;
  loading: boolean;
  onFocusCluster: (cluster: ClusterRecord) => void;
  onClearCluster: () => void;
  onOpen: (id: string) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd?: () => void;
}) {
  const [visibleCount, setVisibleCount] = useState(EXPLORE_PAGE_SIZE);
  const loadMoreRef = useRef<HTMLButtonElement | null>(null);
  const directoryScrollRef = useRef(0);
  const previousShowFeedRef = useRef(Boolean(focusedClusterId || hasActiveSearch));
  const previousFeedScopeRef = useRef(`${focusedClusterId || ''}\n${searchQuery}`);
  const nonEmptyClusters = useMemo(() => clusters.filter(cluster => cluster.count > 0), [clusters]);
  const focusedCluster = useMemo(
    () => clusters.find(cluster => cluster.id === focusedClusterId),
    [clusters, focusedClusterId],
  );
  const previewMetadata = useMemo(() => imageMetadata(items), [items]);
  const showFeed = Boolean(focusedClusterId || hasActiveSearch);
  const visibleItems = useMemo(() => items.slice(0, visibleCount), [items, visibleCount]);
  const hasMore = showFeed && visibleCount < items.length;
  const feedTitle = focusedCluster?.name || (focusedClusterId ? t('collections') : t('allReferences'));

  useEffect(() => {
    setVisibleCount(EXPLORE_PAGE_SIZE);
  }, [focusedClusterId, hasActiveSearch, searchQuery, items]);

  useEffect(() => {
    const previouslyShowingFeed = previousShowFeedRef.current;
    if (!previouslyShowingFeed && showFeed) {
      directoryScrollRef.current = window.scrollY;
      window.scrollTo({ top: 0, behavior: 'auto' });
      previousShowFeedRef.current = true;
    } else if (previouslyShowingFeed && !showFeed && !loading) {
      window.requestAnimationFrame(() => window.scrollTo({ top: directoryScrollRef.current, behavior: 'auto' }));
      previousShowFeedRef.current = false;
    }

    const nextScope = `${focusedClusterId || ''}\n${searchQuery}`;
    if (showFeed && previousFeedScopeRef.current !== nextScope) {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }
    previousFeedScopeRef.current = nextScope;
  }, [focusedClusterId, loading, searchQuery, showFeed]);

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

  if (loading) return null;

  if (!showFeed && !nonEmptyClusters.length) {
    const libraryIsEmpty = total === 0;
    return (
      <div className="empty">
        <h2>{t(libraryIsEmpty ? 'libraryEmptyTitle' : 'noCollectionsFound')}</h2>
        <p>{libraryIsEmpty ? t('libraryEmptyHelp') : `${total} ${t('referencesShown')}`}</p>
        <div className="empty-actions">
          {libraryIsEmpty && onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
        </div>
      </div>
    );
  }

  if (showFeed) {
    return (
      <section className="explore-feed" aria-label={feedTitle}>
        <header className="explore-feed-header">
          <div>
            <p className="explore-eyebrow">{t('explore')}</p>
            <h2>{feedTitle}</h2>
            <p>{total} {t('referencesShown')}</p>
          </div>
          {focusedClusterId && (
            <button type="button" className="explore-back-button" onClick={onClearCluster}>
              <ArrowLeft size={17} aria-hidden="true" />
              {t('collections')}
            </button>
          )}
        </header>

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
    <section className="explore-directory" aria-labelledby="explore-directory-title">
      <header className="explore-directory-header">
        <p className="explore-eyebrow">{t('explore')}</p>
        <h2 id="explore-directory-title">{t('collections')}</h2>
      </header>
      <div className="explore-collection-grid">
        {nonEmptyClusters.map(cluster => {
          const previews = cluster.preview_images.slice(0, 3);
          return (
            <button
              key={cluster.id}
              type="button"
              className="explore-collection-card"
              onClick={() => onFocusCluster(cluster)}
              aria-label={`${cluster.name}, ${cluster.count} ${t('referencesShown')}`}
            >
              <span className="explore-collection-heading">
                <strong>{cluster.name}</strong>
                <span>{cluster.count} {t('referencesShown')}</span>
              </span>
              <span className={`explore-collection-previews preview-count-${previews.length}`} aria-hidden="true">
                {previews.length ? previews.map((path, index) => {
                  const metadata = previewMetadata.get(path);
                  return (
                    <span className="explore-collection-preview" key={`${cluster.id}-${path}-${index}`}>
                      <img
                        src={mediaUrl(path)}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        width={metadata?.width || undefined}
                        height={metadata?.height || undefined}
                      />
                    </span>
                  );
                }) : <span className="explore-collection-placeholder">{t('noImage')}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
