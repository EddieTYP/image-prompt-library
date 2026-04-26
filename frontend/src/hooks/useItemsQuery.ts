import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ItemList } from '../types';

type QueryScope = {
  q: string;
  clusterId?: string;
  tag?: string;
  viewLimit: number;
};

export function useItemsQuery(q: string, clusterId?: string, tag?: string, viewLimit = 100, reloadKey = 0) {
  const [data, setData] = useState<ItemList>({ items: [], total: 0, limit: viewLimit, offset: 0 });
  const [dataScope, setDataScope] = useState<QueryScope>({ q: '', clusterId: undefined, tag: undefined, viewLimit });
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

    api.items({ q, cluster: clusterId, tag, limit: viewLimit })
      .then(nextData => {
        if (!cancelled) {
          setData(nextData);
          setDataScope({ q, clusterId, tag, viewLimit });
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
  }, [q, clusterId, tag, viewLimit, reloadKey]);

  return { data, loading, initialLoading, refreshing, error, dataScope };
}
