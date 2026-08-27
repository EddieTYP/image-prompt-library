import { Check, FolderInput, Plus, Search, Tags, X } from 'lucide-react';
import { useMemo, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useModalFocus } from '../hooks/useModalFocus';
import type { ClusterRecord, TagRecord } from '../types';
import type { Translator } from '../utils/i18n';

type BatchActionMode = 'tags' | 'move';

function cleanTagName(value: string) {
  return value.trim().replace(/^#+/, '').trim();
}

export default function BatchActionDialog({
  mode,
  selectedCount,
  tags,
  clusters,
  busy,
  t,
  onClose,
  onApplyTags,
  onApplyCollection,
}: {
  mode: BatchActionMode;
  selectedCount: number;
  tags: TagRecord[];
  clusters: ClusterRecord[];
  busy: boolean;
  t: Translator;
  onClose: () => void;
  onApplyTags: (tagNames: string[]) => Promise<void>;
  onApplyCollection: (cluster: ClusterRecord) => Promise<void>;
}) {
  const [query, setQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedClusterId, setSelectedClusterId] = useState<string>();
  const close = () => { if (!busy) onClose(); };
  const { containerRef, handleModalKeyDown } = useModalFocus<HTMLElement>(close, {
    fallbackFocusSelector: '.selection-toolbar',
  });
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredTags = useMemo(() => tags
    .filter(tag => !normalizedQuery || tag.name.toLocaleLowerCase().includes(normalizedQuery))
    .slice(0, 40), [normalizedQuery, tags]);
  const filteredClusters = useMemo(() => clusters
    .filter(cluster => !normalizedQuery || cluster.name.toLocaleLowerCase().includes(normalizedQuery))
    .slice(0, 40), [clusters, normalizedQuery]);
  const selectedTagKeys = useMemo(() => new Set(selectedTags.map(tag => tag.toLocaleLowerCase())), [selectedTags]);
  const newTagName = cleanTagName(query);
  const canAddNewTag = mode === 'tags'
    && Boolean(newTagName)
    && !tags.some(tag => tag.name.toLocaleLowerCase() === newTagName.toLocaleLowerCase())
    && !selectedTagKeys.has(newTagName.toLocaleLowerCase());
  const selectedCluster = clusters.find(cluster => cluster.id === selectedClusterId);

  const toggleTag = (name: string) => {
    const key = name.toLocaleLowerCase();
    setSelectedTags(current => current.some(tag => tag.toLocaleLowerCase() === key)
      ? current.filter(tag => tag.toLocaleLowerCase() !== key)
      : [...current, name]);
  };
  const addNewTag = () => {
    if (!canAddNewTag) return;
    setSelectedTags(current => [...current, newTagName]);
    setQuery('');
  };
  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && canAddNewTag) {
      event.preventDefault();
      addNewTag();
    }
  };
  const handleBackdropClick = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) close();
  };
  const submit = async () => {
    if (busy) return;
    if (mode === 'tags' && selectedTags.length) await onApplyTags(selectedTags);
    if (mode === 'move' && selectedCluster) await onApplyCollection(selectedCluster);
  };
  const title = mode === 'tags' ? t('batchTagTitle') : t('batchMoveTitle');
  const applyLabel = mode === 'tags' ? t('applyTags') : t('moveReferences');

  return (
    <div className="modal-backdrop batch-action-backdrop" onMouseDown={handleBackdropClick}>
      <section
        ref={containerRef}
        className="batch-action-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-action-title"
        aria-busy={busy}
        tabIndex={-1}
        onKeyDown={handleModalKeyDown}
      >
        <header className="batch-action-header">
          <span className="batch-action-icon" aria-hidden="true">{mode === 'tags' ? <Tags size={18} /> : <FolderInput size={18} />}</span>
          <span>
            <h2 id="batch-action-title">{title}</h2>
            <p>{selectedCount} {t('selectedReferences')}</p>
          </span>
          <button type="button" className="modal-icon-button batch-action-close" onClick={close} aria-label={t('close')} disabled={busy}><X size={18} /></button>
        </header>

        <label className="batch-action-search">
          <Search size={17} aria-hidden="true" />
          <input
            data-modal-initial-focus
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder={mode === 'tags' ? t('searchOrCreateTags') : t('searchCollections')}
          />
        </label>

        {mode === 'tags' && selectedTags.length > 0 && (
          <div className="batch-selected-tags" aria-label={t('selectedTags')}>
            {selectedTags.map(tag => (
              <button type="button" key={tag} onClick={() => toggleTag(tag)} disabled={busy}>#{tag}<X size={13} /></button>
            ))}
          </div>
        )}

        <div className="batch-action-options" role={mode === 'tags' ? 'group' : 'radiogroup'} aria-label={title}>
          {mode === 'tags' && canAddNewTag && (
            <button type="button" className="batch-action-option batch-create-tag" onClick={addNewTag} disabled={busy}>
              <Plus size={17} /><span>{t('createTag').replace('${tag}', newTagName)}</span>
            </button>
          )}
          {mode === 'tags' && filteredTags.map(tag => {
            const selected = selectedTagKeys.has(tag.name.toLocaleLowerCase());
            return (
              <button type="button" className={`batch-action-option${selected ? ' selected' : ''}`} key={tag.id} onClick={() => toggleTag(tag.name)} aria-pressed={selected} disabled={busy}>
                <span>#{tag.name}</span><small>{tag.count}</small>{selected && <Check size={17} />}
              </button>
            );
          })}
          {mode === 'move' && filteredClusters.map(cluster => {
            const selected = selectedClusterId === cluster.id;
            return (
              <button type="button" className={`batch-action-option batch-collection-option${selected ? ' selected' : ''}`} key={cluster.id} role="radio" aria-checked={selected} onClick={() => setSelectedClusterId(cluster.id)} disabled={busy}>
                <span>{cluster.name}</span><small>{cluster.count} {t('referencesShown')}</small>{selected && <Check size={17} />}
              </button>
            );
          })}
          {((mode === 'tags' && !canAddNewTag && filteredTags.length === 0) || (mode === 'move' && filteredClusters.length === 0)) && (
            <p className="batch-action-empty">{mode === 'tags' ? t('noTagsFound') : t('noCollectionsFound')}</p>
          )}
        </div>

        <footer className="batch-action-footer">
          <button type="button" className="secondary" onClick={close} disabled={busy}>{t('cancel')}</button>
          <button type="button" className="primary" onClick={submit} disabled={busy || (mode === 'tags' ? selectedTags.length === 0 : !selectedCluster)}>
            {busy ? t('saving') : applyLabel}
          </button>
        </footer>
      </section>
    </div>
  );
}
