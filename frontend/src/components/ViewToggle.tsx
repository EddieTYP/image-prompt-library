import type { ViewMode } from '../types';
import type { Translator } from '../utils/i18n';

export default function ViewToggle({ view, onView, t }: { view: ViewMode; onView: (view: ViewMode) => void; t: Translator }) {
  return (
    <div className="toggle" role="group" aria-label={t('primaryNavigation')}>
      <button type="button" className={view === 'explore' ? 'active' : ''} aria-pressed={view === 'explore'} onClick={() => onView('explore')}>{t('explore')}</button>
      <button type="button" className={view === 'cards' ? 'active' : ''} aria-pressed={view === 'cards'} onClick={() => onView('cards')}>{t('cards')}</button>
    </div>
  );
}
