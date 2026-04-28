import type { PromptRecord, UiLanguage } from '../types';

export type PromptLanguage = 'zh_hant' | 'zh_hans' | 'en';
export type PromptCopyLanguage = PromptLanguage | 'origin';

export const PROMPT_LANGUAGE_LABELS: Record<PromptLanguage, string> = {
  zh_hant: '繁中',
  zh_hans: '簡中',
  en: 'English',
};

export const PROMPT_COPY_LANGUAGE_LABELS: Record<UiLanguage, Record<PromptCopyLanguage, string>> = {
  zh_hant: { origin: '原文', en: '英文', zh_hant: '繁中', zh_hans: '簡中' },
  zh_hans: { origin: '原文', en: '英文', zh_hant: '繁中', zh_hans: '简中' },
  en: { origin: 'Origin', en: 'English', zh_hant: 'zh-Hant', zh_hans: 'zh-Hans' },
};

export function getPromptCopyLanguageLabel(language: PromptCopyLanguage, uiLanguage: UiLanguage): string {
  return PROMPT_COPY_LANGUAGE_LABELS[uiLanguage]?.[language] || PROMPT_COPY_LANGUAGE_LABELS.en[language];
}

export const DEFAULT_PROMPT_LANGUAGE: PromptCopyLanguage = 'origin';

export function normalizePromptLanguage(value?: string | null): PromptCopyLanguage {
  if (value === 'origin' || value === 'zh_hant' || value === 'zh_hans' || value === 'en') return value;
  return DEFAULT_PROMPT_LANGUAGE;
}

export function resolveOriginalPrompt<T extends Pick<PromptRecord, 'language' | 'text' | 'is_original'>>(
  prompts: T[] | undefined,
): T | undefined {
  const usable = (prompts || []).filter(prompt => prompt.text.trim().length > 0);
  return usable.find(prompt => prompt.is_original) || usable.find(prompt => prompt.language === 'en') || usable[0];
}

export function resolvePromptText(
  prompts: Array<Pick<PromptRecord, 'language' | 'text' | 'is_original'>> | undefined,
  preferredLanguage: PromptCopyLanguage,
  fallbackTitle = '',
): string {
  const usable = (prompts || []).filter(prompt => prompt.text.trim().length > 0);
  if (preferredLanguage === 'origin') return resolveOriginalPrompt(usable)?.text || fallbackTitle;
  const preferred = usable.find(prompt => prompt.language === preferredLanguage);
  const english = usable.find(prompt => prompt.language === 'en');
  const original = resolveOriginalPrompt(usable);
  const anyPrompt = usable[0];
  return preferred?.text || english?.text || original?.text || anyPrompt?.text || fallbackTitle;
}
