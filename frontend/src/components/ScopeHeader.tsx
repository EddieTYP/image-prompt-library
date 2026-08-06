import { useId } from 'react';
import { ArrowLeft, ChevronDown } from 'lucide-react';
import type { ItemSortMode } from '../types';
import type { Translator } from '../utils/i18n';

export default function ScopeHeader({
  t,
  title,
  count,
  countLabel,
  sort,
  onSort,
  backLabel,
  onBack,
}: {
  t: Translator;
  title: string;
  count: number;
  countLabel: string;
  sort?: ItemSortMode;
  onSort?: (sort: ItemSortMode) => void;
  backLabel?: string;
  onBack?: () => void;
}) {
  const showSort = Boolean(sort && onSort);
  const sortId = useId();

  return (
    <header className={`scope-header${onBack ? ' has-back' : ''}`}>
      <div className="scope-heading">
        <h1>{title}</h1>
        <span className="scope-count">
          <span aria-hidden="true">· </span>
          {count}
          <span className="sr-only"> {countLabel}</span>
        </span>
      </div>
      {(onBack || showSort) && (
        <div className={`scope-actions${onBack ? ' has-back' : ''}`}>
          {onBack && backLabel && (
            <button type="button" className="scope-back-button" onClick={onBack}>
              <ArrowLeft size={16} aria-hidden="true" />
              {backLabel}
            </button>
          )}
          {showSort && (
            <label className="scope-sort-control" htmlFor={sortId}>
              <span className="scope-sort-prefix">{t('sortChip')}</span>
              <span className="scope-sort-picker">
                <select
                  id={sortId}
                  className="scope-sort-select"
                  value={sort}
                  onChange={event => onSort?.(event.currentTarget.value as ItemSortMode)}
                  aria-label={t('sortChip')}
                >
                  <option value="updated_desc">{t('sortByUpdated')}</option>
                  <option value="created_desc">{t('sortByCreated')}</option>
                  <option value="created_asc">{t('sortByOldest')}</option>
                  <option value="title_asc">{t('sortByTitle')}</option>
                  <option value="title_desc">{t('sortByTitleDesc')}</option>
                  <option value="source_asc">{t('sortBySource')}</option>
                  <option value="model_asc">{t('sortByModel')}</option>
                </select>
                <ChevronDown size={14} aria-hidden="true" />
              </span>
            </label>
          )}
        </div>
      )}
    </header>
  );
}
