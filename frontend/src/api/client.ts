import type { AppConfig, AppUpdateRequest, AppUpdateResult, AppUpdateStatus, CleanupApplyRequest, CleanupApplyResult, CleanupPreview, ClusterRecord, CodexNativeAuthPollRequest, CodexNativeAuthPollResponse, CodexNativeAuthStart, GenerationJobAcceptAsNewItemPayload, GenerationJobAcceptResult, GenerationJobCreate, GenerationJobList, GenerationJobRecord, GenerationJobRetryResult, GenerationJobSetCreate, GenerationJobSetRecord, GenerationProviderStatus, GrokOAuthPollRequest, ItemBatchRequest, ItemBatchResult, ItemCreate, ItemDetail, ItemImageUpdate, ItemList, ItemSortMode, ItemSummary, ProviderDeviceAuthStart, TagRecord, TitleSuggestionRequest, TitleSuggestionResponse, UploadImageRole } from '../types';
import { DEFAULT_ITEM_SORT } from '../utils/searchSort';

const API = '';
const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_DATA_BASE = `${import.meta.env.BASE_URL || '/'}demo-data`.replace(/\/+/g, '/');

async function responseError(response: Response) {
  const body = await response.text();
  try {
    const payload = JSON.parse(body) as { detail?: unknown };
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail;
  } catch {
    // Keep plain-text provider and server errors unchanged.
  }
  return body || `${response.status} ${response.statusText}`;
}

function demoUrl(path: string) {
  const base = import.meta.env.BASE_URL || '/';
  return `${base}${path.replace(/^\/+/, '')}`;
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + url, { headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) throw new Error(await responseError(r));
  return r.json();
}

async function demoJson<T>(path: string): Promise<T> {
  const r = await fetch(demoUrl(path));
  if (!r.ok) throw new Error(await responseError(r));
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

function normalizeDemoText(value?: string) {
  return (value || '').toLowerCase();
}

function demoItemSort(sort: ItemSortMode) {
  if (sort === 'created_desc') return (a: ItemSummary, b: ItemSummary) => b.created_at.localeCompare(a.created_at);
  if (sort === 'created_asc') return (a: ItemSummary, b: ItemSummary) => a.created_at.localeCompare(b.created_at);
  if (sort === 'title_asc') return (a: ItemSummary, b: ItemSummary) => a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });
  if (sort === 'title_desc') return (a: ItemSummary, b: ItemSummary) => b.title.localeCompare(a.title, undefined, { sensitivity: 'base' });
  if (sort === 'source_asc') return (a: ItemSummary, b: ItemSummary) => (a.source_name || '').localeCompare(b.source_name || '', undefined, { sensitivity: 'base' });
  if (sort === 'model_asc') return (a: ItemSummary, b: ItemSummary) => a.model.localeCompare(b.model, undefined, { sensitivity: 'base' });
  return (a: ItemSummary, b: ItemSummary) => b.updated_at.localeCompare(a.updated_at);
}

function demoStructuredSearch(rawQuery: string) {
  const filters: Record<string, string[]> = {};
  const q = rawQuery.replace(/(?:^|\s)(tag|collection|model|source|fav|favorite|archived|has):([^\s]+)/gi, (_match, key: string, value: string) => {
    const normalizedKey = key.toLowerCase();
    (filters[normalizedKey] ||= []).push(value.toLowerCase());
    return ' ';
  }).replace(/\s+/g, ' ').trim().toLowerCase();
  return { q, filters };
}

function demoMatchesStructuredSearch(item: ItemSummary, filters: Record<string, string[]>) {
  if (filters.tag?.some(tag => !item.tags.some(itemTag => normalizeDemoText(itemTag.name).includes(tag) || normalizeDemoText(itemTag.id).includes(tag)))) return false;
  if (filters.collection?.some(collection => !normalizeDemoText(item.cluster?.name).includes(collection) && !normalizeDemoText(item.cluster?.id).includes(collection))) return false;
  if (filters.model?.some(model => !normalizeDemoText(item.model).includes(model))) return false;
  if (filters.source?.some(source => !normalizeDemoText(item.source_name).includes(source))) return false;
  if (filters.has?.includes('image') && !item.first_image) return false;
  if (filters.has?.includes('prompt') && !item.prompts.some(prompt => prompt.text.trim())) return false;
  if ((filters.fav?.includes('true') || filters.favorite?.includes('true')) && !item.favorite) return false;
  if ((filters.fav?.includes('false') || filters.favorite?.includes('false')) && item.favorite) return false;
  if (filters.archived?.includes('true') && !item.archived) return false;
  if (filters.archived?.includes('false') && item.archived) return false;
  return true;
}

async function demoItemList(params: Record<string, string | number | boolean | undefined>): Promise<ItemList> {
  const allItems = await demoItems();
  const structured = demoStructuredSearch(String(params.q || ''));
  const q = structured.q;
  const cluster = String(params.cluster || '').trim();
  const tag = String(params.tag || '').trim();
  const sort = (['updated_desc', 'created_desc', 'created_asc', 'title_asc', 'title_desc', 'source_asc', 'model_asc'].includes(String(params.sort))) ? params.sort as ItemSortMode : DEFAULT_ITEM_SORT;
  const limit = Math.max(0, Number(params.limit || 100));
  const offset = Math.max(0, Number(params.offset || 0));
  const filtered = allItems.filter(item => {
    if (cluster && item.cluster?.id !== cluster) return false;
    if (tag && !item.tags.some(itemTag => itemTag.name === tag || itemTag.id === tag)) return false;
    if (!demoMatchesStructuredSearch(item, structured.filters)) return false;
    if (q && !normalizeSearchText(item).includes(q)) return false;
    return true;
  });
  return { items: filtered.sort(demoItemSort(sort)).slice(offset, offset + limit), total: filtered.length, limit, offset };
}

async function demoItem(id: string): Promise<ItemDetail> {
  const allItems = await demoItems();
  const item = allItems.find(candidate => candidate.id === id);
  if (!item) throw new Error('Demo item not found');
  return { ...item, images: item.first_image ? [item.first_image] : [], notes: 'Online Read Only Demo sample. Demo images are compressed; run the app locally for your own private full library.', author: (item as ItemDetail).author };
}

function demoReadOnly(): Promise<never> {
  return Promise.reject(new Error('The online sandbox is read-only. Run Image Prompt Library locally to create your own private library.'));
}

export class TitleSuggestionRequestError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'TitleSuggestionRequestError';
  }
}

async function suggestTitleRequest(payload: TitleSuggestionRequest): Promise<TitleSuggestionResponse> {
  const response = await fetch(`${API}/api/generation-providers/openai-codex-native/suggest-title`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let message = '';
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === 'string') message = body.detail;
    } catch {
      message = '';
    }
    throw new TitleSuggestionRequestError(response.status, message || 'Title suggestion failed.');
  }
  return response.json();
}

export const mediaUrl = (path?: string) => {
  if (!path) return '';
  if (isDemoMode && path.startsWith('demo-data/')) return demoUrl(path);
  return `/media/${path}`;
};

export const api = isDemoMode ? {
  health: () => Promise.resolve({ ok: true, version: 'demo' }),
  config: () => Promise.resolve<AppConfig>({ version: 'demo', library_path: 'GitHub Pages read-only sandbox', database_path: 'Static JSON bundle', preferred_prompt_language: 'en', features: { camelot: { percival: true } } }),
  updateStatus: (_refresh = false) => Promise.resolve<AppUpdateStatus>({ current_version: 'demo', latest_version: null, update_available: false, checked_at: new Date().toISOString(), error: null, update_capability: 'command_only', update_reason: 'demo_mode', service_mode: 'not_applicable', active_generation_jobs: { running: 0, queued: 0 }, can_restart: false, requires_manual_restart: true }),
  startAppUpdate: (_payload: AppUpdateRequest) => demoReadOnly(),
  cleanupPreview: () => Promise.resolve<CleanupPreview>({ broken_image_records: [], unreferenced_files: [], total_bytes: 0, preview_token: 'demo' }),
  applyCleanup: (_payload: CleanupApplyRequest) => demoReadOnly(),
  items: demoItemList,
  item: demoItem,
  createItem: (_payload: ItemCreate) => demoReadOnly(),
  updateItem: (_id: string, _payload: Partial<ItemCreate>) => demoReadOnly(),
  deleteItem: (_id: string) => demoReadOnly(),
  batchItems: (_payload: ItemBatchRequest) => demoReadOnly(),
  favorite: (_id: string) => demoReadOnly(),
  uploadImage: (_id: string, _file: File, _role: UploadImageRole = 'result_image') => demoReadOnly(),
  updateImages: (_id: string, _images: ItemImageUpdate[]) => demoReadOnly(),
  generationProviders: () => Promise.resolve<GenerationProviderStatus[]>([
    {
      provider: 'manual_upload',
      display_name: 'Manual upload',
      optional: false,
      configured: true,
      authenticated: true,
      available: true,
      state: 'available',
      status: 'ready',
      message: null,
      can_generate: true,
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
      status: 'unavailable',
      message: 'Generation requires a local install.',
      can_generate: false,
      reason: 'local_only',
      features: { text_to_image: false, text_reference_to_image: false, image_edit: false },
      max_input_images: 4,
      token_present: false,
      account_id: null,
    },
    {
      provider: 'xai_grok_oauth',
      display_name: 'Grok OAuth · Experimental',
      auth_mode: 'grok_oauth_device',
      optional: true,
      configured: true,
      authenticated: false,
      available: false,
      state: 'demo_unavailable',
      status: 'unavailable',
      message: 'Generation requires a local install.',
      can_generate: false,
      reason: 'local_only',
      features: { text_to_image: false, text_reference_to_image: false, image_edit: false },
      max_input_images: 3,
      token_present: false,
    },
  ]),
  codexNativeAuthStart: () => demoReadOnly(),
  codexNativeAuthPoll: (_payload: CodexNativeAuthPollRequest) => demoReadOnly(),
  codexNativeAuthDisconnect: () => demoReadOnly(),
  grokOAuthAuthStart: () => demoReadOnly(),
  grokOAuthAuthPoll: (_payload: GrokOAuthPollRequest) => demoReadOnly(),
  grokOAuthAuthDisconnect: () => demoReadOnly(),
  suggestTitle: (_payload: TitleSuggestionRequest) => demoReadOnly(),
  generationJobs: () => Promise.resolve<GenerationJobList>({
    jobs: [],
    total: 0,
    limit: 100,
    offset: 0,
    status_counts: { queued: 0, running: 0, succeeded: 0, failed: 0, accepted: 0, discarded: 0, cancelled: 0 },
    generation_sets: [],
    provider_queue_states: [],
  }),
  generationJob: (_id: string) => demoReadOnly(),
  createGenerationJob: (_payload: GenerationJobCreate) => demoReadOnly(),
  createGenerationSet: (_payload: GenerationJobSetCreate) => demoReadOnly(),
  generationSet: (_id: string) => demoReadOnly(),
  cancelRemainingGenerationSet: (_id: string) => demoReadOnly(),
  runGenerationJob: (_id: string) => demoReadOnly(),
  uploadGenerationResult: (_id: string, _file: File) => demoReadOnly(),
  acceptGenerationJob: (_id: string) => demoReadOnly(),
  acceptGenerationJobIntoItem: (_id: string, _itemId: string) => demoReadOnly(),
  acceptGenerationJobAsNewItem: (_id: string, _payload?: GenerationJobAcceptAsNewItemPayload) => demoReadOnly(),
  cancelGenerationJob: (_id: string) => demoReadOnly(),
  retryGenerationJob: (_id: string) => demoReadOnly(),
  markGenerationJobFailed: (_id: string) => demoReadOnly(),
  discardGenerationJob: (_id: string) => demoReadOnly(),
  discardAndRetryGenerationJob: (_id: string) => demoReadOnly(),
  clusters: () => demoJson<ClusterRecord[]>('demo-data/clusters.json'),
  tags: () => demoJson<TagRecord[]>('demo-data/tags.json'),
} : {
  health: () => json<{ok: boolean; version: string}>('/api/health'),
  config: () => json<AppConfig>('/api/config'),
  updateStatus: (refresh = false) => json<AppUpdateStatus>(refresh ? '/api/update-status?refresh=true' : '/api/update-status'),
  startAppUpdate: (payload: AppUpdateRequest) => json<AppUpdateResult>('/api/app-update/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  cleanupPreview: () => json<CleanupPreview>('/api/cleanup/preview'),
  applyCleanup: (payload: CleanupApplyRequest) => json<CleanupApplyResult>('/api/cleanup/apply', { method: 'POST', body: JSON.stringify(payload) }),
  items: (params: Record<string, string | number | boolean | undefined>) => { const qs = new URLSearchParams(); Object.entries(params).forEach(([k,v]) => { if (v !== undefined && v !== '') qs.set(k, String(v)); }); return json<ItemList>(`/api/items?${qs}`); },
  item: (id: string) => json<ItemDetail>(`/api/items/${id}`),
  createItem: (payload: ItemCreate) => json<ItemDetail>('/api/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateItem: (id: string, payload: Partial<ItemCreate>) => json<ItemDetail>(`/api/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteItem: (id: string) => json<ItemDetail>(`/api/items/${id}`, { method: 'DELETE' }),
  batchItems: (payload: ItemBatchRequest) => json<ItemBatchResult>('/api/items/batch', { method: 'POST', body: JSON.stringify(payload) }),
  favorite: (id: string) => json<ItemDetail>(`/api/items/${id}/favorite`, { method: 'POST' }),
  uploadImage: (id: string, file: File, role: UploadImageRole = 'result_image') => { const fd = new FormData(); fd.set('file', file); fd.set('role', role); return json(`/api/items/${id}/images`, { method: 'POST', body: fd }); },
  updateImages: (id: string, images: ItemImageUpdate[]) => json<ItemDetail>(`/api/items/${id}/images`, { method: 'PUT', body: JSON.stringify({ images }) }),
  generationProviders: () => json<GenerationProviderStatus[]>('/api/generation-providers'),
  codexNativeAuthStart: () => json<CodexNativeAuthStart>('/api/generation-providers/openai-codex-native/auth/start', { method: 'POST' }),
  codexNativeAuthPoll: (payload: CodexNativeAuthPollRequest) => json<CodexNativeAuthPollResponse>('/api/generation-providers/openai-codex-native/auth/poll', { method: 'POST', body: JSON.stringify(payload) }),
  codexNativeAuthDisconnect: () => json<GenerationProviderStatus>('/api/generation-providers/openai-codex-native/auth/disconnect', { method: 'POST' }),
  grokOAuthAuthStart: () => json<ProviderDeviceAuthStart>('/api/generation-providers/xai-grok-oauth/auth/start', { method: 'POST' }),
  grokOAuthAuthPoll: (payload: GrokOAuthPollRequest) => json<CodexNativeAuthPollResponse>('/api/generation-providers/xai-grok-oauth/auth/poll', { method: 'POST', body: JSON.stringify(payload) }),
  grokOAuthAuthDisconnect: () => json<GenerationProviderStatus>('/api/generation-providers/xai-grok-oauth/auth/disconnect', { method: 'POST' }),
  suggestTitle: suggestTitleRequest,
  generationJobs: (params: Record<string, string | number | boolean | undefined> = {}) => { const qs = new URLSearchParams(); Object.entries(params).forEach(([k,v]) => { if (v !== undefined && v !== '') qs.set(k, String(v)); }); return json<GenerationJobList>(`/api/generation-jobs?${qs}`); },
  generationJob: (id: string) => json<GenerationJobRecord>(`/api/generation-jobs/${id}`),
  createGenerationJob: (payload: GenerationJobCreate) => json<GenerationJobRecord>('/api/generation-jobs', { method: 'POST', body: JSON.stringify(payload) }),
  createGenerationSet: (payload: GenerationJobSetCreate) => json<GenerationJobSetRecord>('/api/generation-jobs/sets', { method: 'POST', body: JSON.stringify(payload) }),
  generationSet: (id: string) => json<GenerationJobSetRecord>(`/api/generation-jobs/sets/${id}`),
  cancelRemainingGenerationSet: (id: string) => json<GenerationJobSetRecord>(`/api/generation-jobs/sets/${id}/cancel-remaining`, { method: 'POST' }),
  runGenerationJob: (id: string) => json<GenerationJobRecord>(`/api/generation-jobs/${id}/run`, { method: 'POST' }),
  uploadGenerationResult: (id: string, file: File) => { const fd = new FormData(); fd.set('file', file); return json<GenerationJobRecord>(`/api/generation-jobs/${id}/result`, { method: 'POST', body: fd }); },
  acceptGenerationJob: (id: string) => json<GenerationJobAcceptResult>(`/api/generation-jobs/${id}/accept`, { method: 'POST' }),
  acceptGenerationJobIntoItem: (id: string, itemId: string) => json<GenerationJobAcceptResult>(`/api/generation-jobs/${id}/accept-into-item`, { method: 'POST', body: JSON.stringify({ item_id: itemId }) }),
  acceptGenerationJobAsNewItem: (id: string, payload: GenerationJobAcceptAsNewItemPayload = {}) => json<GenerationJobAcceptResult>(`/api/generation-jobs/${id}/accept-as-new-item`, { method: 'POST', body: JSON.stringify(payload) }),
  cancelGenerationJob: (id: string) => json<GenerationJobRecord>(`/api/generation-jobs/${id}/cancel`, { method: 'POST' }),
  retryGenerationJob: (id: string) => json<GenerationJobRecord>(`/api/generation-jobs/${id}/retry`, { method: 'POST' }),
  markGenerationJobFailed: (id: string) => json<GenerationJobRecord>(`/api/generation-jobs/${id}/mark-failed`, { method: 'POST' }),
  discardGenerationJob: (id: string) => json<GenerationJobRecord>(`/api/generation-jobs/${id}/discard`, { method: 'POST' }),
  discardAndRetryGenerationJob: (id: string) => json<GenerationJobRetryResult>(`/api/generation-jobs/${id}/discard-and-retry`, { method: 'POST' }),
  clusters: () => json<ClusterRecord[]>('/api/clusters'),
  tags: () => json<TagRecord[]>('/api/tags'),
};

export { DEMO_DATA_BASE, isDemoMode };
