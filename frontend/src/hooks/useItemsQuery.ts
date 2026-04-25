import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ItemList } from '../types';
export function useItemsQuery(q: string, clusterId?: string, tag?: string, viewLimit = 100, reloadKey = 0) { const [data, setData] = useState<ItemList>({items:[], total:0, limit:viewLimit, offset:0}); const [loading, setLoading] = useState(false); const [error, setError] = useState<string>(); useEffect(() => { setLoading(true); setError(undefined); api.items({ q, cluster: clusterId, tag, limit: viewLimit }).then(setData).catch(e => setError(String(e))).finally(() => setLoading(false)); }, [q, clusterId, tag, viewLimit, reloadKey]); return {data, loading, error}; }
