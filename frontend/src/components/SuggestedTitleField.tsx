import { useEffect, useId, useRef, useState } from 'react';
import { api, TitleSuggestionRequestError } from '../api/client';
import type { Translator } from '../utils/i18n';

export default function SuggestedTitleField({
  value,
  promptText,
  t,
  onChange,
  autoFocus = false,
  className = '',
}: {
  value: string;
  promptText: string;
  t: Translator;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  className?: string;
}) {
  const [suggestion, setSuggestion] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const promptRef = useRef(promptText);
  const inputId = useId();

  useEffect(() => {
    promptRef.current = promptText;
    setSuggestion('');
    setError('');
  }, [promptText]);

  const requestSuggestion = async () => {
    const requestedPrompt = promptText.trim();
    if (!requestedPrompt || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.suggestTitle({ prompt_text: requestedPrompt });
      if (promptRef.current.trim() === requestedPrompt) setSuggestion(result.title);
    } catch (requestError) {
      if (promptRef.current.trim() !== requestedPrompt) return;
      if (requestError instanceof TitleSuggestionRequestError) {
        if (requestError.status === 409) setError(t('titleSuggestionLoginRequired'));
        else if (requestError.status === 429) setError(t('titleSuggestionRateLimited'));
        else if (requestError.status === 503) setError(t('titleSuggestionUnavailable'));
        else setError(t('titleSuggestionFailed'));
      } else {
        setError(t('titleSuggestionFailed'));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`suggested-title-field ${className}`.trim()}>
      <div className="suggested-title-label-row">
        <label htmlFor={inputId}>{t('title')}</label>
        <button type="button" className="suggest-title-button" onClick={requestSuggestion} disabled={busy || !promptText.trim()}>
          {busy ? t('suggestingTitle') : t('suggestTitle')}
        </button>
      </div>
      <input id={inputId} data-modal-initial-focus={autoFocus || undefined} placeholder={t('titlePlaceholder')} value={value} onChange={event => onChange(event.currentTarget.value)} />
      {suggestion && (
        <div className="title-suggestion" role="status">
          <span><b>{t('suggestedTitle')}</b>{suggestion}</span>
          <button type="button" onClick={() => { onChange(suggestion); setSuggestion(''); }}>{t('useSuggestedTitle')}</button>
        </div>
      )}
      {error && <p className="title-suggestion-error" role="alert">{error}</p>}
    </div>
  );
}
