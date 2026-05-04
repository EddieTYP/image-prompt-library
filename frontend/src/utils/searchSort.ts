import type { ItemSortMode } from '../types';
import type { Translator } from './i18n';

export const DEFAULT_ITEM_SORT: ItemSortMode = 'updated_desc';

const SORT_OPERATOR_RE = /(?:^|\s)sort:(updated|created|title)(?=\s|$)/gi;

const SORT_OPERATORS: Record<string, ItemSortMode> = {
  'sort:updated': 'updated_desc',
  'sort:created': 'created_desc',
  'sort:title': 'title_asc',
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

export function sortLabelForMode(sort: ItemSortMode, t: Translator) {
  if (sort === 'created_desc') return t('sortByCreated');
  if (sort === 'title_asc') return t('sortByTitle');
  return t('sortByUpdated');
}
