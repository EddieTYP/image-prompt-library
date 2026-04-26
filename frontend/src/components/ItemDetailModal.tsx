import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Check, Copy, ExternalLink, Heart, Pencil, Plus, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import type { ClusterRecord, ImageRecord, ItemDetail, TagRecord } from '../types';
import { copyTextToClipboard } from '../utils/clipboard';
import { imageDisplayPath, imageHeroPath, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';
import { PROMPT_LANGUAGE_LABELS, resolvePromptText, type PromptLanguage } from '../utils/prompts';

const LANG_LABELS: Record<string, string> = {
  ...PROMPT_LANGUAGE_LABELS,
  en: 'ENG',
};
const promptDisplayOrder = ['en', 'zh_hant', 'zh_hans'];

function getImageIdentity(image: ImageRecord) {
  return image.thumb_path || image.preview_path || image.original_path || image.id;
}

function dedupeImages(images: ImageRecord[]) {
  const seenImageKeys = new Set<string>();
  return images.filter(image => {
    const key = getImageIdentity(image);
    if (seenImageKeys.has(key)) return false;
    seenImageKeys.add(key);
    return true;
  });
}

function resolvePromptRecord<T extends { language: string; text: string }>(
  prompts: T[],
  selectedLanguage: string,
  preferredLanguage: PromptLanguage,
): T | undefined {
  const usable = prompts.filter(prompt => prompt.text.trim().length > 0);
  return usable.find(prompt => prompt.language === selectedLanguage)
    || usable.find(prompt => prompt.language === preferredLanguage)
    || usable.find(prompt => prompt.language === 'en')
    || usable[0];
}

function InlineEditableField({
  className,
  value,
  placeholder,
  inputList,
  onCommit,
  children,
}: {
  className: string;
  value: string;
  placeholder?: string;
  inputList?: string;
  onCommit: (value: string) => void;
  children?: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = () => { onCommit(draft); setEditing(false); };
  const cancel = () => { setDraft(value); setEditing(false); };
  if (editing) {
    return (
      <span className={`inline-editable ${className} is-editing`}>
        <input
          value={draft}
          placeholder={placeholder}
          list={inputList}
          autoFocus
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') confirm();
            if (event.key === 'Escape') cancel();
          }}
        />
        {children}
        <span className="inline-edit-controls">
          <button type="button" className="inline-edit-confirm" onClick={confirm} aria-label="Confirm edit"><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} aria-label="Cancel edit"><X size={14} /></button>
        </span>
      </span>
    );
  }
  return (
    <span className={`inline-editable ${className}`} onDoubleClick={() => setEditing(true)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') setEditing(true); }}>
      {value || placeholder}
    </span>
  );
}

function InlineEditableTextArea({
  className,
  value,
  placeholder,
  onCommit,
}: {
  className: string;
  value: string;
  placeholder?: string;
  onCommit: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = () => { onCommit(draft); setEditing(false); };
  const cancel = () => { setDraft(value); setEditing(false); };
  if (editing) {
    return (
      <div className={`inline-editable ${className} is-editing`}>
        <textarea
          value={draft}
          placeholder={placeholder}
          autoFocus
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') confirm();
            if (event.key === 'Escape') cancel();
          }}
        />
        <span className="inline-edit-controls">
          <button type="button" className="inline-edit-confirm" onClick={confirm} aria-label="Confirm edit"><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} aria-label="Cancel edit"><X size={14} /></button>
        </span>
      </div>
    );
  }
  return (
    <div className={`inline-editable ${className} ${value ? '' : 'notes-empty'}`} onDoubleClick={() => setEditing(true)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') setEditing(true); }}>
      {value ? <p>{value}</p> : <span className="add-note-affordance">{placeholder}</span>}
    </div>
  );
}

export default function ItemDetailModal({
  id,
  t,
  preferredLanguage,
  clusters,
  tags,
  onClose,
  onCopyPrompt,
  onEdit,
  onChanged,
}: {
  id?: string;
  t: Translator;
  preferredLanguage: PromptLanguage;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  onClose: () => void;
  onCopyPrompt: (success: boolean) => void;
  onEdit: (item: ItemDetail) => void;
  onChanged: () => void;
}) {
  const [item, setItem] = useState<ItemDetail>();
  const [lang, setLang] = useState<string>(preferredLanguage);
  const [addingTag, setAddingTag] = useState(false);
  const [tagQuery, setTagQuery] = useState('');
  const [editingPromptLanguage, setEditingPromptLanguage] = useState<string>();
  const [promptDraft, setPromptDraft] = useState('');
  const lastDefaultPromptKeyRef = useRef('');

  useEffect(() => { setLang(preferredLanguage); }, [preferredLanguage, id]);

  useEffect(() => {
    if (!id) return;
    setItem(undefined);
    api.item(id).then(setItem);
  }, [id]);

  const availablePromptRecords = useMemo(() => {
    if (!item) return [];
    return promptDisplayOrder
      .map(promptLanguage => item.prompts.find(prompt => prompt.language === promptLanguage && prompt.text.trim().length > 0))
      .filter((prompt): prompt is NonNullable<typeof prompt> => Boolean(prompt));
  }, [item]);

  useEffect(() => {
    if (!item || !id) return;
    const defaultPromptKey = `${id}:${preferredLanguage}`;
    if (lastDefaultPromptKeyRef.current === defaultPromptKey) return;
    const nextPrompt = resolvePromptRecord(availablePromptRecords, preferredLanguage, preferredLanguage);
    if (nextPrompt) setLang(nextPrompt.language);
    lastDefaultPromptKeyRef.current = defaultPromptKey;
  }, [item, availablePromptRecords, preferredLanguage, id]);

  const filteredTagSuggestions = useMemo(() => {
    if (!item) return [];
    const existing = new Set(item.tags.map(tag => tag.name));
    const query = tagQuery.trim().toLowerCase();
    return tags
      .filter(tag => !existing.has(tag.name) && (!query || tag.name.toLowerCase().includes(query)))
      .slice(0, 8);
  }, [item, tags, tagQuery]);

  if (!id) return null;

  const prompt = item?.prompts.find(promptRecord => promptRecord.language === lang);
  const resolvedPrompt = resolvePromptRecord(availablePromptRecords, lang, preferredLanguage);
  const copyText = prompt?.text || resolvedPrompt?.text || resolvePromptText(item?.prompts, preferredLanguage, item?.title || '');
  const uniqueImages = dedupeImages(item?.images || []);
  const primaryImage = selectPrimaryImage(uniqueImages);
  const commitInlineUpdate = async (payload: Record<string, unknown>) => {
    if (!item) return;
    const updated = await api.updateItem(item.id, payload);
    setItem(updated);
    onChanged();
  };
  const handleCopyPrompt = async (text = copyText) => {
    const copied = await copyTextToClipboard(text);
    onCopyPrompt(copied);
  };
  const commitPrompt = (language: string, text: string) => {
    if (!item) return;
    const merged = new Map(item.prompts.map(existing => [existing.language, existing.text]));
    if (text.trim()) merged.set(language, text.trim());
    else merged.delete(language);
    const orderedPromptTexts = promptDisplayOrder.map(promptLanguage => ({ promptLanguage, text: merged.get(promptLanguage)?.trim() || '' }));
    const primaryLanguage = orderedPromptTexts.find(nextPrompt => nextPrompt.text)?.promptLanguage;
    const prompts = orderedPromptTexts
      .map(nextPrompt => ({ language: nextPrompt.promptLanguage, text: nextPrompt.text, is_primary: nextPrompt.promptLanguage === primaryLanguage }))
      .filter(nextPrompt => nextPrompt.text);
    commitInlineUpdate({ prompts });
  };
  const startPromptEdit = (language: string, text: string) => {
    setEditingPromptLanguage(language);
    setPromptDraft(text);
  };
  const cancelPromptEdit = () => {
    setEditingPromptLanguage(undefined);
    setPromptDraft('');
  };
  const confirmPromptEdit = () => {
    if (!editingPromptLanguage) return;
    commitPrompt(editingPromptLanguage, promptDraft);
    cancelPromptEdit();
  };
  const unlinkTag = (tagName: string) => {
    if (!item) return;
    commitInlineUpdate({ tags: item.tags.filter(tag => tag.name !== tagName).map(tag => tag.name) });
  };
  const addTag = (tagName: string) => {
    if (!item) return;
    const nextTag = tagName.trim();
    if (!nextTag) return;
    const nextTags = Array.from(new Set([...item.tags.map(tag => tag.name), nextTag]));
    commitInlineUpdate({ tags: nextTags });
    setAddingTag(false);
    setTagQuery('');
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="detail modal polished-modal" onClick={e => e.stopPropagation()}>
        {!item ? (
          <p className="modal-loading">{t('loading')}</p>
        ) : (
          <div className="modal-content-enter" key={item.id}>
            <div className="detail-layout">
              <section className="modal-hero">
                {primaryImage ? (
                  <img
                    className="hero-image"
                    src={mediaUrl(imageHeroPath(primaryImage))}
                    alt={item.title}
                  />
                ) : (
                  <div className="placeholder hero-image">{t('noImage')}</div>
                )}
                {uniqueImages.length > 1 && (
                  <div className="rail glass-rail">
                    {uniqueImages.map(img => (
                      <img key={getImageIdentity(img)} src={mediaUrl(imageDisplayPath(img))} alt="" />
                    ))}
                  </div>
                )}
              </section>

              <aside className="detail-side">
                <div className="detail-side-actions">
                  <span className="detail-side-primary-actions">
                    <button className="modal-icon-button favorite-button" onClick={() => api.favorite(item.id).then(updated => { setItem(updated); onChanged(); })} aria-label={item.favorite ? t('saved') : t('favorite')}>
                      <Heart size={18} fill={item.favorite ? 'currentColor' : 'none'} />
                    </button>
                    <button className="modal-icon-button edit-button" onClick={() => onEdit(item)} aria-label={t('edit')}>
                      <Pencil size={18} />
                    </button>
                  </span>
                  <button className="modal-icon-button close" onClick={onClose} aria-label={t('close')}>
                    <X size={20} />
                  </button>
                </div>
                <InlineEditableField className="collection-inline-edit" value={item.cluster?.name || ''} placeholder={t('unclustered')} inputList="detail-collection-suggestions" onCommit={value => commitInlineUpdate({ cluster_name: value.trim() || null })}>
                  <datalist id="detail-collection-suggestions">
                    {clusters.map(collection => <option key={collection.id} value={collection.name} />)}
                  </datalist>
                </InlineEditableField>
                <h2>
                  <InlineEditableField className="title-inline-edit" value={item.title} placeholder={t('titlePlaceholder')} onCommit={value => commitInlineUpdate({ title: value.trim() || item.title })} />
                </h2>
                <p className="muted metadata-row">
                  <InlineEditableField className="metadata-inline-edit" value={item.model || t('defaultModel')} placeholder={t('imageGeneratedFrom')} onCommit={value => commitInlineUpdate({ model: value.trim() || item.model })} />
                  <span>·</span>
                  <InlineEditableField className="metadata-inline-edit" value={`@${item.author || 'User'}`} placeholder="@User" onCommit={value => commitInlineUpdate({ author: value.replace(/^@/, '').trim() || 'User' })} />
                  {item.source_url && (
                    <a className="source-icon-link" href={item.source_url} target="_blank" rel="noreferrer" aria-label={t('source')}>
                      <ExternalLink size={16} />
                    </a>
                  )}
                </p>

                <div className="prompt-blocks" aria-label={t('promptLanguage')}>
                  {(() => {
                    return (
                      <section className="prompt-block prompt-panel active">
                        <header className="prompt-block-header">
                          <div className="prompt-language-tabs tabs" role="tablist" aria-label={t('promptLanguage')}>
                            {promptDisplayOrder.map(promptLanguage => {
                              const tabPrompt = item.prompts.find(prompt => prompt.language === promptLanguage);
                              return (
                                <button
                                  type="button"
                                  role="tab"
                                  aria-selected={lang === promptLanguage}
                                  className={`prompt-language-tab ${lang === promptLanguage ? 'active' : ''}`}
                                  onClick={() => { setLang(promptLanguage); cancelPromptEdit(); }}
                                  title={tabPrompt?.text.trim() ? undefined : t('promptText')}
                                  key={promptLanguage}
                                >
                                  {LANG_LABELS[promptLanguage] || promptLanguage}
                                </button>
                              );
                            })}
                          </div>
                          <span className="prompt-block-actions">
                            <button type="button" className="prompt-copy-icon" onClick={() => handleCopyPrompt(prompt?.text || '')} aria-label={t('copyPrompt')} disabled={!prompt?.text}>
                              <Copy size={15} />
                            </button>
                            <button type="button" className="prompt-edit-icon" onClick={() => startPromptEdit(lang, prompt?.text || '')} aria-label={t('edit')}>
                              <Pencil size={15} />
                            </button>
                          </span>
                        </header>
                        <div className="prompt-panel-body">
                          {editingPromptLanguage === lang ? (
                            <>
                              <textarea
                                className="prompt-edit-textarea"
                                value={promptDraft}
                                placeholder={t('promptText')}
                                autoFocus
                                onChange={event => setPromptDraft(event.target.value)}
                                onKeyDown={event => {
                                  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') confirmPromptEdit();
                                  if (event.key === 'Escape') cancelPromptEdit();
                                }}
                              />
                              <span className="prompt-edit-controls">
                                <button type="button" className="inline-edit-confirm" onClick={confirmPromptEdit} aria-label="Confirm edit"><Check size={14} /></button>
                                <button type="button" className="inline-edit-cancel" onClick={cancelPromptEdit} aria-label="Cancel edit"><X size={14} /></button>
                              </span>
                            </>
                          ) : (
                            <div className={`prompt-inline-edit ${prompt?.text ? '' : 'notes-empty'}`} onDoubleClick={() => startPromptEdit(lang, prompt?.text || '')} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') startPromptEdit(lang, prompt?.text || ''); }}>
                              {prompt?.text ? <p>{prompt.text}</p> : <span className="add-note-affordance">{t('promptText')}</span>}
                            </div>
                          )}
                        </div>
                      </section>
                    );
                  })()}
                </div>

                <InlineEditableTextArea className="notes-inline-edit" value={item.notes || ''} placeholder={t('addNote')} onCommit={value => commitInlineUpdate({ notes: value.trim() || null })} />

                <div className="tags detail-tags">
                  {item.tags.map(tag => (
                    <span className="detail-tag-chip" key={tag.id}>#{tag.name}<button type="button" className="tag-unlink-button" onClick={() => unlinkTag(tag.name)} aria-label={`Remove ${tag.name}`}><X size={12} /></button></span>
                  ))}
                  {addingTag ? (
                    <span className="tag-add-popover">
                      <input className="tag-add-input" autoFocus value={tagQuery} onChange={event => setTagQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') addTag(tagQuery); if (event.key === 'Escape') setAddingTag(false); }} placeholder={t('tags')} />
                      <button type="button" className="inline-edit-confirm" onClick={() => addTag(tagQuery)}><Check size={12} /></button>
                      <button type="button" className="inline-edit-cancel" onClick={() => setAddingTag(false)}><X size={12} /></button>
                      {filteredTagSuggestions.length > 0 && <span className="tag-add-suggestions">{filteredTagSuggestions.map(tag => <button type="button" key={tag.id} onClick={() => addTag(tag.name)}>#{tag.name}</button>)}</span>}
                    </span>
                  ) : (
                    <button type="button" className="add-tag-chip" onClick={() => setAddingTag(true)} aria-label={t('tags')}><Plus size={14} /></button>
                  )}
                </div>
              </aside>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
