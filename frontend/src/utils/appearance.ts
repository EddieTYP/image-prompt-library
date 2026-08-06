import type { AppearancePreset } from '../types';

export const APPEARANCE_STORAGE_KEY = 'image-prompt-library.appearance.v1';
export const DEFAULT_APPEARANCE: AppearancePreset = 'gallery_vermilion';

export function normalizeAppearance(value: string | null | undefined): AppearancePreset {
  if (value === 'pine_archive' || value === 'aubergine_ink') return value;
  return DEFAULT_APPEARANCE;
}

export function loadAppearance(): AppearancePreset {
  if (typeof window === 'undefined') return DEFAULT_APPEARANCE;
  return normalizeAppearance(window.localStorage.getItem(APPEARANCE_STORAGE_KEY));
}

export function applyAppearance(appearance: AppearancePreset) {
  document.documentElement.dataset.appearance = appearance;
}

export function applyStoredAppearance() {
  if (typeof document === 'undefined') return;
  applyAppearance(loadAppearance());
}
