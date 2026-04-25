import { useEffect, useState } from 'react';
export function useDebouncedValue<T>(value: T, delay = 250) { const [debounced, setDebounced] = useState(value); useEffect(() => { const t = window.setTimeout(() => setDebounced(value), delay); return () => window.clearTimeout(t); }, [value, delay]); return debounced; }
