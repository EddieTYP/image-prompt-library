export const GENERATION_QUALITY_STORAGE_KEY = 'image-prompt-library.generation_quality';

export function normalizeGenerationQuality(value: string | null): string {
  return value === 'low' || value === 'medium' || value === 'high' ? value : 'high';
}

export function loadGenerationQuality(): string {
  try {
    return normalizeGenerationQuality(window.localStorage.getItem(GENERATION_QUALITY_STORAGE_KEY));
  } catch {
    return 'high';
  }
}

export function saveGenerationQuality(value: string): void {
  try {
    window.localStorage.setItem(GENERATION_QUALITY_STORAGE_KEY, normalizeGenerationQuality(value));
  } catch {
    // A blocked storage area must not prevent generation in this session.
  }
}
