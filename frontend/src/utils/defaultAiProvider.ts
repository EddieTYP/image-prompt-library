import type { GenerationProviderStatus, TitleSuggestionProvider } from '../types';

export const DEFAULT_AI_PROVIDER_STORAGE_KEY = 'image-prompt-library.default_ai_provider';
export const FALLBACK_AI_PROVIDER: TitleSuggestionProvider = 'openai_codex_oauth_native';

export function isTitleSuggestionProvider(value: string | null | undefined): value is TitleSuggestionProvider {
  return value === 'openai_codex_oauth_native' || value === 'xai_grok_oauth';
}

export function availableTitleSuggestionProviders(providers: GenerationProviderStatus[]): TitleSuggestionProvider[] {
  return providers
    .filter(provider =>
      isTitleSuggestionProvider(provider.provider)
      && provider.configured
      && provider.authenticated
      && provider.available
      && provider.features.title_suggestion,
    )
    .map(provider => provider.provider as TitleSuggestionProvider);
}

export function resolveDefaultAiProvider(
  storedProvider: string | null | undefined,
  providers: GenerationProviderStatus[],
): TitleSuggestionProvider {
  if (isTitleSuggestionProvider(storedProvider)) return storedProvider;
  const available = availableTitleSuggestionProviders(providers);
  return available.length === 1 ? available[0] : FALLBACK_AI_PROVIDER;
}
