import { useEffect, useState } from 'react';
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

  useEffect(() => {
    let cancelled = false;
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

    return () => { cancelled = true; };
  }, [q, clusterId, tag, viewLimit, reloadKey, sort]);

  return { data, loading, initialLoading, refreshing, error, dataScope };
}
