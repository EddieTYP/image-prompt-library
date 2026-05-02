import { isDemoMode } from '../api/client';
import type { ItemSummary, UiLanguage } from '../types';

export function localizedDemoTitle(item: Pick<ItemSummary, 'title' | 'demo_titles'>, uiLanguage: UiLanguage): string {
  if (!isDemoMode) return item.title;
  return item.demo_titles?.[uiLanguage] || item.demo_titles?.en || item.title;
}
