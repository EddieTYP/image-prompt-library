import type { PromptRecord } from '../types';

export type PromptLanguage = 'zh_hant' | 'zh_hans' | 'en';

export const PROMPT_LANGUAGE_LABELS: Record<PromptLanguage, string> = {
  zh_hant: '繁中',
  zh_hans: '簡中',
  en: 'English',
};

export const DEFAULT_PROMPT_LANGUAGE: PromptLanguage = 'zh_hant';

export function normalizePromptLanguage(value?: string | null): PromptLanguage {
  if (value === 'zh_hant' || value === 'zh_hans' || value === 'en') return value;
  return DEFAULT_PROMPT_LANGUAGE;
}

export function resolvePromptText(
  prompts: Array<Pick<PromptRecord, 'language' | 'text'>> | undefined,
  preferredLanguage: PromptLanguage,
  fallbackTitle = '',
): string {
  const usable = (prompts || []).filter(prompt => prompt.text.trim().length > 0);
  const preferred = usable.find(prompt => prompt.language === preferredLanguage);
  const english = usable.find(prompt => prompt.language === 'en');
  const anyPrompt = usable[0];
  return preferred?.text || english?.text || anyPrompt?.text || fallbackTitle;
}
