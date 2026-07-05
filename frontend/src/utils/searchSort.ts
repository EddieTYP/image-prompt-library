import type { ItemSortMode } from '../types';
import type { Translator } from './i18n';

export const DEFAULT_ITEM_SORT: ItemSortMode = 'updated_desc';

const SORT_OPERATOR_RE = /(?:^|\s)sort:(updated|created|oldest|title|title-desc|source|model)(?=\s|$)/gi;
const STRUCTURED_FILTER_RE = /(?:^|[\s,])((created|updated|tag|collection|model|source|fav|favorite|has):[^\s,]+)/gi;

const SORT_OPERATORS: Record<string, ItemSortMode> = {
  'sort:updated': 'updated_desc',
  'sort:created': 'created_desc',
  'sort:oldest': 'created_asc',
  'sort:title': 'title_asc',
  'sort:title-desc': 'title_desc',
  'sort:source': 'source_asc',
  'sort:model': 'model_asc',
};

export type ParsedSearchSortQuery = {
  q: string;
  sort: ItemSortMode;
  explicitSort: boolean;
};

function normalizeSearchWhitespace(value: string) {
  return value.replace(/\s+/g, ' ').trim();
}

export function parseSearchSortQuery(rawQuery: string): ParsedSearchSortQuery {
  let sort: ItemSortMode = DEFAULT_ITEM_SORT;
  let explicitSort = false;
  const q = normalizeSearchWhitespace(rawQuery.replace(SORT_OPERATOR_RE, match => {
    const token = match.trim().toLowerCase();
    sort = SORT_OPERATORS[token] || DEFAULT_ITEM_SORT;
    explicitSort = true;
    return ' ';
  }));
  return { q, sort, explicitSort };
}

export function removeSearchSortOperator(rawQuery: string) {
  return normalizeSearchWhitespace(rawQuery.replace(SORT_OPERATOR_RE, ' '));
}

export function parseStructuredSearchChips(rawQuery: string): string[] {
  const chips: string[] = [];
  for (const match of rawQuery.matchAll(STRUCTURED_FILTER_RE)) {
    const token = match[1];
    const [key, value = ''] = token.split(':', 2);
    const normalizedKey = key.toLowerCase();
    const normalizedValue = value.toLowerCase();
    if (
      ['created', 'updated', 'tag', 'collection', 'model', 'source'].includes(normalizedKey) ||
      (['fav', 'favorite'].includes(normalizedKey) && ['true', 'false'].includes(normalizedValue)) ||
      (normalizedKey === 'has' && normalizedValue === 'image')
    ) {
      chips.push(token);
    }
  }
  return chips;
}

export function sortLabelForMode(sort: ItemSortMode, t: Translator) {
  if (sort === 'created_desc') return t('sortByCreated');
  if (sort === 'created_asc') return t('sortByOldest');
  if (sort === 'title_asc') return t('sortByTitle');
  if (sort === 'title_desc') return t('sortByTitleDesc');
  if (sort === 'source_asc') return t('sortBySource');
  if (sort === 'model_asc') return t('sortByModel');
  return t('sortByUpdated');
}
