import type { AppConfig, ClusterRecord, CodexNativeAuthPollRequest, CodexNativeAuthPollResponse, CodexNativeAuthStart, GenerationProviderStatus, ItemCreate, ItemDetail, ItemList, ItemSummary, TagRecord, UploadImageRole } from '../types';

const API = '';
const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_DATA_BASE = `${import.meta.env.BASE_URL || '/'}demo-data`.replace(/\/+/g, '/');

function demoUrl(path: string) {
  const base = import.meta.env.BASE_URL || '/';
  return `${base}${path.replace(/^\/+/, '')}`;
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + url, { headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function demoJson<T>(path: string): Promise<T> {
  const r = await fetch(demoUrl(path));
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

let demoItemsCache: Promise<ItemSummary[]> | undefined;
const demoItems = () => demoItemsCache ||= demoJson<ItemSummary[]>('demo-data/items.json');

function normalizeSearchText(item: ItemSummary) {
  return [
    item.title,
    item.cluster?.name,
    item.source_name,
    item.model,
    ...item.tags.map(tag => tag.name),
    ...item.prompts.map(prompt => prompt.text),
  ].filter(Boolean).join('\n').toLowerCase();
}

async function demoItemList(params: Record<string, string | number | boolean | undefined>): Promise<ItemList> {
  const allItems = await demoItems();
  const q = String(params.q || '').trim().toLowerCase();
  const cluster = String(params.cluster || '').trim();
  const tag = String(params.tag || '').trim();
  const limit = Math.max(0, Number(params.limit || 100));
  const offset = Math.max(0, Number(params.offset || 0));
  const filtered = allItems.filter(item => {
    if (cluster && item.cluster?.id !== cluster) return false;
    if (tag && !item.tags.some(itemTag => itemTag.name === tag || itemTag.id === tag)) return false;
    if (q && !normalizeSearchText(item).includes(q)) return false;
    return true;
  });
  return { items: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset };
}

async function demoItem(id: string): Promise<ItemDetail> {
  const allItems = await demoItems();
  const item = allItems.find(candidate => candidate.id === id);
  if (!item) throw new Error('Demo item not found');
  return { ...item, images: item.first_image ? [item.first_image] : [], notes: 'Online sandbox sample. Images are compressed for the web demo; run the app locally for your own private full library.', author: (item as ItemDetail).author };
}

function demoReadOnly(): Promise<never> {
  return Promise.reject(new Error('The online sandbox is read-only. Run Image Prompt Library locally to create your own private library.'));
}

export const mediaUrl = (path?: string) => {
  if (!path) return '';
  if (isDemoMode && path.startsWith('demo-data/')) return demoUrl(path);
  return `/media/${path}`;
};

export const api = isDemoMode ? {
  health: () => Promise.resolve({ ok: true, version: 'demo' }),
  config: () => Promise.resolve<AppConfig>({ version: 'demo', library_path: 'GitHub Pages read-only sandbox', database_path: 'Static JSON bundle', preferred_prompt_language: 'en' }),
  items: demoItemList,
  item: demoItem,
  createItem: (_payload: ItemCreate) => demoReadOnly(),
  updateItem: (_id: string, _payload: Partial<ItemCreate>) => demoReadOnly(),
  deleteItem: (_id: string) => demoReadOnly(),
  favorite: (_id: string) => demoReadOnly(),
  uploadImage: (_id: string, _file: File, _role: UploadImageRole = 'result_image') => demoReadOnly(),
  generationProviders: () => Promise.resolve<GenerationProviderStatus[]>([
    {
      provider: 'manual_upload',
      display_name: 'Manual upload',
      optional: false,
      configured: true,
      authenticated: true,
      available: true,
      state: 'available',
      reason: null,
      features: { manual_result_upload: true },
    },
    {
      provider: 'openai_codex_oauth_native',
      display_name: 'ChatGPT / Codex OAuth',
      auth_mode: 'codex_oauth_native',
      optional: true,
      configured: false,
      authenticated: false,
      available: false,
      state: 'demo_unavailable',
      reason: 'local_only',
      features: { text_to_image: false, text_reference_to_image: false, image_edit: false },
      token_present: false,
      account_id: null,
    },
  ]),
  codexNativeAuthStart: () => demoReadOnly(),
  codexNativeAuthPoll: (_payload: CodexNativeAuthPollRequest) => demoReadOnly(),
  codexNativeAuthDisconnect: () => demoReadOnly(),
  clusters: () => demoJson<ClusterRecord[]>('demo-data/clusters.json'),
  tags: () => demoJson<TagRecord[]>('demo-data/tags.json'),
} : {
  health: () => json<{ok: boolean; version: string}>('/api/health'),
  config: () => json<AppConfig>('/api/config'),
  items: (params: Record<string, string | number | boolean | undefined>) => { const qs = new URLSearchParams(); Object.entries(params).forEach(([k,v]) => { if (v !== undefined && v !== '') qs.set(k, String(v)); }); return json<ItemList>(`/api/items?${qs}`); },
  item: (id: string) => json<ItemDetail>(`/api/items/${id}`),
  createItem: (payload: ItemCreate) => json<ItemDetail>('/api/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateItem: (id: string, payload: Partial<ItemCreate>) => json<ItemDetail>(`/api/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteItem: (id: string) => json<ItemDetail>(`/api/items/${id}`, { method: 'DELETE' }),
  favorite: (id: string) => json<ItemDetail>(`/api/items/${id}/favorite`, { method: 'POST' }),
  uploadImage: (id: string, file: File, role: UploadImageRole = 'result_image') => { const fd = new FormData(); fd.set('file', file); fd.set('role', role); return json(`/api/items/${id}/images`, { method: 'POST', body: fd }); },
  generationProviders: () => json<GenerationProviderStatus[]>('/api/generation-providers'),
  codexNativeAuthStart: () => json<CodexNativeAuthStart>('/api/generation-providers/openai-codex-native/auth/start', { method: 'POST' }),
  codexNativeAuthPoll: (payload: CodexNativeAuthPollRequest) => json<CodexNativeAuthPollResponse>('/api/generation-providers/openai-codex-native/auth/poll', { method: 'POST', body: JSON.stringify(payload) }),
  codexNativeAuthDisconnect: () => json<GenerationProviderStatus>('/api/generation-providers/openai-codex-native/auth/disconnect', { method: 'POST' }),
  clusters: () => json<ClusterRecord[]>('/api/clusters'),
  tags: () => json<TagRecord[]>('/api/tags'),
};

export { DEMO_DATA_BASE, isDemoMode };
