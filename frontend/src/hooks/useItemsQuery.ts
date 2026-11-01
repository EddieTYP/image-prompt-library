import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ItemList, ItemSortMode } from '../types';
import { DEFAULT_ITEM_SORT } from '../utils/searchSort';

type QueryScope = {
  q: string;
  clusterId?: string;
  tag?: string;
  viewLimit: number;
  sort: ItemSortMode;
};

export function useItemsQuery(q: string, clusterId?: string, tag?: string, viewLimit = 100, reloadKey = 0, sort: ItemSortMode = DEFAULT_ITEM_SORT) {
  const [data, setData] = useState<ItemList>({ items: [], total: 0, limit: viewLimit, offset: 0 });
  const [dataScope, setDataScope] = useState<QueryScope>({ q: '', clusterId: undefined, tag: undefined, viewLimit, sort });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string>();
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string>();
  const [hasMore, setHasMore] = useState(false);
  const [appendVersion, setAppendVersion] = useState(0);
  const requestGeneration = useRef(0);
  const loadingMoreRef = useRef(false);
  const nextOffset = useRef(0);

  useEffect(() => {
    let cancelled = false;
    requestGeneration.current += 1;
    loadingMoreRef.current = false;
    setLoadingMore(false);
    setLoadMoreError(undefined);
    setHasMore(false);
    setAppendVersion(0);
    const hasVisibleData = data.items.length > 0 || data.total > 0;
    setLoading(true);
    setInitialLoading(!hasVisibleData);
    setRefreshing(hasVisibleData);
    setError(undefined);

    api.items({ q, cluster: clusterId, tag, limit: viewLimit, sort })
      .then(nextData => {
        if (!cancelled) {
          setData(nextData);
          setDataScope({ q, clusterId, tag, viewLimit, sort });
          nextOffset.current = nextData.offset + nextData.items.length;
          setHasMore(nextData.items.length > 0 && nextOffset.current < nextData.total);
        }
      })
      .catch(e => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setInitialLoading(false);
          setRefreshing(false);
        }
      });

    return () => { cancelled = true; requestGeneration.current += 1; };
  }, [q, clusterId, tag, viewLimit, reloadKey, sort]);

  const loadMore = async () => {
    if (loadingMoreRef.current || loading || !hasMore || dataScope.q !== q
      || dataScope.clusterId !== clusterId || dataScope.tag !== tag
      || dataScope.viewLimit !== viewLimit || dataScope.sort !== sort) return;
    const generation = requestGeneration.current;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setLoadMoreError(undefined);
    try {
      const page = await api.items({ q, cluster: clusterId, tag, limit: viewLimit, sort, offset: nextOffset.current });
      if (generation !== requestGeneration.current) return;
      nextOffset.current = page.offset + page.items.length;
      setData(current => {
        const seen = new Set(current.items.map(item => item.id));
        const added = page.items.filter(item => {
          if (seen.has(item.id)) return false;
          seen.add(item.id);
          return true;
        });
        return { ...current, total: page.total, items: [...current.items, ...added] };
      });
      setHasMore(page.items.length > 0 && nextOffset.current < page.total);
      setAppendVersion(version => version + 1);
      return page.items.find(item => !data.items.some(existing => existing.id === item.id))?.id;
    } catch (e) {
      if (generation === requestGeneration.current) setLoadMoreError(String(e));
    } finally {
      if (generation === requestGeneration.current) {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      }
    }
  };

  return { data, loading, initialLoading, refreshing, error, dataScope, loadMore, loadingMore, loadMoreError, hasMore, appendVersion };
}
