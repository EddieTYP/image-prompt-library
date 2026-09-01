import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ImagePlus, Star, Trash2, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import { useModalFocus } from '../hooks/useModalFocus';
import type { ClusterRecord, ImageRecord, ItemDetail, TagRecord, TitleSuggestionProvider, UploadImageRole } from '../types';
import { imageThumbnailPath } from '../utils/images';
import type { Translator } from '../utils/i18n';
import SuggestedTitleField from './SuggestedTitleField';

function promptText(item: ItemDetail | undefined, language: string) {
  return item?.prompts.find(prompt => prompt.language === language)?.text || '';
}

function initialTraditionalPrompt(item: ItemDetail | undefined) {
  return promptText(item, 'zh_hant') || promptText(item, 'original');
}

function initialOriginalLanguage(item: ItemDetail | undefined) {
  const original = item?.prompts.find(prompt => prompt.is_original);
  if (original?.language === 'en' || original?.language === 'zh_hant' || original?.language === 'zh_hans') return original.language;
  return 'en';
}

function promptProvenance(language: string, originalLanguage: string) {
  if (language === originalLanguage) return { kind: 'manual', source_language: language, derived_from: null, method: null };
  return { kind: 'manual', source_language: originalLanguage, derived_from: originalLanguage, method: null };
}

export default function ItemEditorModal({
  item,
  t,
  clusters,
  tags: existingTags,
  defaultAiProvider,
  onClose,
  onSaved,
  onDeleted,
  allowDelete = true,
}: {
  item?: ItemDetail;
  t: Translator;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  defaultAiProvider: TitleSuggestionProvider;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  allowDelete?: boolean;
}) {
  const [persistedItem, setPersistedItem] = useState(item);
  const [title, setTitle] = useState(item?.title || '');
  const [model, setModel] = useState(item?.model || 'ChatGPT');
  const [author, setAuthor] = useState(item?.author || 'User');
  const [sourceUrl, setSourceUrl] = useState(item?.source_url || '');
  const [notes, setNotes] = useState(item?.notes || '');
  const [cluster, setCluster] = useState(item?.cluster?.name || '');
  const [tags, setTags] = useState(item?.tags.map(t => t.name).join(', ') || '');
  const [zhHantPrompt, setZhHantPrompt] = useState(initialTraditionalPrompt(item));
  const [zhHansPrompt, setZhHansPrompt] = useState(promptText(item, 'zh_hans'));
  const [englishPrompt, setEnglishPrompt] = useState(promptText(item, 'en'));
  const [originalLanguage, setOriginalLanguage] = useState(initialOriginalLanguage(item));
  const [resultFile, setResultFile] = useState<File>();
  const [referenceFile, setReferenceFile] = useState<File>();
  const [imageDrafts, setImageDrafts] = useState<ImageRecord[]>(item?.images || []);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  const beginClose = () => {
    if (isClosing) return;
    setIsClosing(true);
    const delay = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 180;
    window.setTimeout(onClose, delay);
  };
  const handleClose = () => {
    if (saving || deleting) return;
    beginClose();
  };
  const editorFallbackSelector = '.card-open-hit, .add-fab, .empty-primary';
  const { containerRef: editorDialogRef, handleModalKeyDown } = useModalFocus<HTMLDivElement>(handleClose, { fallbackFocusSelector: editorFallbackSelector });

  const hasExistingResultImage = imageDrafts.some(image => image.role === 'result_image');
  const hasPrompt = Boolean(zhHantPrompt.trim() || zhHansPrompt.trim() || englishPrompt.trim());
  const titleSuggestionPrompt = (
    originalLanguage === 'zh_hant' ? zhHantPrompt
      : originalLanguage === 'zh_hans' ? zhHansPrompt
        : englishPrompt
  ).trim() || englishPrompt.trim() || zhHantPrompt.trim() || zhHansPrompt.trim();
  const missingRequiredImage = !hasExistingResultImage && !resultFile;
  const [saveError, setSaveError] = useState('');
  const filteredClusters = useMemo(() => {
    const query = cluster.trim().toLowerCase();
    if (!query) return clusters.slice(0, 8);
    return clusters.filter(c => c.name.toLowerCase().includes(query)).slice(0, 8);
  }, [cluster, clusters]);
  const filteredTags = useMemo(() => {
    const selected = new Set(tags.split(',').map(t => t.trim()).filter(Boolean));
    const query = tags.split(',').pop()?.trim().toLowerCase() || '';
    return existingTags
      .filter(tag => !selected.has(tag.name) && (!query || tag.name.toLowerCase().includes(query)))
      .slice(0, 10);
  }, [tags, existingTags]);
  const addSuggestedTag = (tagName: string) => {
    const parts = tags.split(',').map(t => t.trim()).filter(Boolean);
    const selected = new Set(parts);
    selected.add(tagName);
    setTags(Array.from(selected).join(', '));
  };
  const primaryImageId = imageDrafts.find(image => image.role === 'result_image')?.id;
  const imageDraftChanged = Boolean(persistedItem) && JSON.stringify(
    imageDrafts.map(image => [image.id, image.role || 'result_image']),
  ) !== JSON.stringify(
    (persistedItem?.images || []).map(image => [image.id, image.role || 'result_image']),
  );
  const normalizeImageDrafts = (images: ImageRecord[]) => [
    ...images.filter(image => image.role !== 'reference_image'),
    ...images.filter(image => image.role === 'reference_image'),
  ];
  const updateImageRole = (imageId: string, role: UploadImageRole) => {
    setSaveError('');
    const image = imageDrafts.find(candidate => candidate.id === imageId);
    if (!image || image.role === role) return;
    if (image.role !== 'reference_image' && role === 'reference_image' && imageDrafts.filter(candidate => candidate.role !== 'reference_image').length === 1) {
      setSaveError(t('keepOneResultImage'));
      return;
    }
    setImageDrafts(current => normalizeImageDrafts(current.map(candidate => candidate.id === imageId ? { ...candidate, role } : candidate)));
  };
  const moveImage = (imageId: string, direction: -1 | 1) => {
    setImageDrafts(current => {
      const index = current.findIndex(image => image.id === imageId);
      if (index < 0) return current;
      const role = current[index].role || 'result_image';
      const sameRoleIndexes = current.map((image, candidateIndex) => ({ image, candidateIndex }))
        .filter(candidate => (candidate.image.role || 'result_image') === role)
        .map(candidate => candidate.candidateIndex);
      const roleIndex = sameRoleIndexes.indexOf(index);
      const swapIndex = sameRoleIndexes[roleIndex + direction];
      if (swapIndex === undefined) return current;
      const next = [...current];
      [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
      return next;
    });
  };
  const makePrimaryImage = (imageId: string) => {
    setImageDrafts(current => {
      const selected = current.find(image => image.id === imageId && image.role !== 'reference_image');
      if (!selected) return current;
      return [selected, ...current.filter(image => image.id !== imageId)];
    });
  };
  const removeImage = (imageId: string) => {
    setSaveError('');
    const image = imageDrafts.find(candidate => candidate.id === imageId);
    if (image?.role !== 'reference_image' && imageDrafts.filter(candidate => candidate.role !== 'reference_image').length === 1) {
      setSaveError(t('keepOneResultImage'));
      return;
    }
    setImageDrafts(current => current.filter(candidate => candidate.id !== imageId));
  };

  const save = async () => {
    if (!title.trim() || !hasPrompt || missingRequiredImage || saving || deleting) return;
    setSaving(true);
    setSaveError('');
    try {
      const promptDrafts = [
        { language: 'en', text: englishPrompt.trim(), is_primary: true },
        { language: 'zh_hant', text: zhHantPrompt.trim(), is_primary: !englishPrompt.trim() },
        { language: 'zh_hans', text: zhHansPrompt.trim(), is_primary: !englishPrompt.trim() && !zhHantPrompt.trim() },
      ];
      const availableOriginal = promptDrafts.find(prompt => prompt.language === originalLanguage && prompt.text)
        ? originalLanguage
        : promptDrafts.find(prompt => prompt.text)?.language || originalLanguage;
      const prompts = promptDrafts
        .filter(prompt => prompt.text)
        .map(prompt => ({
          ...prompt,
          is_original: prompt.language === availableOriginal,
          provenance: promptProvenance(prompt.language, availableOriginal),
        }));
      const payload = {
        title: title.trim(),
        model: model.trim() || undefined,
        author: author.trim() || 'User',
        source_url: sourceUrl.trim() || undefined,
        notes: notes.trim() || undefined,
        cluster_name: cluster.trim() || undefined,
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        prompts,
      };
      const createdNewItem = !persistedItem;
      let saved = persistedItem ? await api.updateItem(persistedItem.id, payload) : await api.createItem(payload);
      if (persistedItem && imageDraftChanged) {
        saved = await api.updateImages(saved.id, imageDrafts.map(image => ({ id: image.id, role: image.role || 'result_image' })));
      }
      setPersistedItem(saved);
      setImageDrafts(saved.images);
      let resultUploaded = false;
      let referenceUploaded = false;
      try {
        if (resultFile) {
          await api.uploadImage(saved.id, resultFile, 'result_image');
          resultUploaded = true;
        }
        if (referenceFile) {
          await api.uploadImage(saved.id, referenceFile, 'reference_image');
          referenceUploaded = true;
        }
      } catch {
        if (createdNewItem) {
          try {
            await api.deleteItem(saved.id);
            setPersistedItem(undefined);
            setSaveError(t('imageUploadFailed'));
          } catch {
            const reconciled = await api.item(saved.id).catch(() => undefined);
            setPersistedItem(reconciled || saved);
            if (resultUploaded && reconciled?.images.some(image => image.role === 'result_image')) setResultFile(undefined);
            if (referenceUploaded && reconciled?.images.some(image => image.role === 'reference_image')) setReferenceFile(undefined);
            onSaved();
            setSaveError(t('saveRollbackFailed'));
          }
          return;
        }
        const reconciled = await api.item(saved.id).catch(() => undefined);
        setPersistedItem(reconciled || saved);
        if (resultUploaded && reconciled?.images.some(image => image.role === 'result_image')) setResultFile(undefined);
        if (referenceUploaded && reconciled?.images.some(image => image.role === 'reference_image')) setReferenceFile(undefined);
        onSaved();
        setSaveError(t('savePartiallyCompleted'));
        return;
      }
      setResultFile(undefined);
      setReferenceFile(undefined);
      onSaved();
      beginClose();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t('saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const deleteReference = async () => {
    if (!allowDelete || !persistedItem || deleting || saving) return;
    if (!confirm(t('deleteReferenceConfirm'))) return;
    setDeleting(true);
    try {
      await api.deleteItem(persistedItem.id);
      onDeleted();
      beginClose();
    } catch {
      setSaveError(t('deleteFailed'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className={`modal-backdrop${isClosing ? ' is-closing' : ''}`} onClick={handleClose}>
      <div
        ref={editorDialogRef}
        className="editor modal polished-modal"
        onClick={event => event.stopPropagation()}
        onKeyDown={handleModalKeyDown}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reference-editor-title"
      >
        <button className="close" onClick={handleClose} aria-label={t('close')}>
          <X size={20} strokeWidth={2.25} />
        </button>
        <div className="editor-head">
          <p className="modal-kicker">{persistedItem ? t('updateReference') : t('newReference')}</p>
          <h2 id="reference-editor-title">{persistedItem ? t('editPromptCard') : t('addPromptCard')}</h2>
          <p>{t('editorHelp')}</p>
        </div>

        <div className="editor-grid">
          <SuggestedTitleField className="field field-title" value={title} promptText={titleSuggestionPrompt} provider={defaultAiProvider} t={t} onChange={setTitle} autoFocus />
          <label className="field">
            <span>{t('collection')}</span>
            <input list="collection-suggestions" placeholder={t('collectionPlaceholder')} value={cluster} onChange={e => setCluster(e.target.value)} />
            <datalist id="collection-suggestions">
              {filteredClusters.map(collection => <option key={collection.id} value={collection.name} />)}
            </datalist>
          </label>
          <label className="field">
            <span>{t('imageGeneratedFrom')}</span>
            <input placeholder={t('defaultModel')} value={model} onChange={e => setModel(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('author')}</span>
            <input placeholder="User" value={author} onChange={e => setAuthor(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('sourceUrl')}</span>
            <input type="url" placeholder="https://…" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} />
          </label>
          <label className="field tag-field">
            <span>{t('tags')}</span>
            <input list="tag-suggestions" placeholder={t('tagsPlaceholder')} value={tags} onChange={e => setTags(e.target.value)} />
            <datalist id="tag-suggestions">
              {filteredTags.map(tag => <option key={tag.id} value={tag.name} />)}
            </datalist>
            {filteredTags.length > 0 && (
              <div className="tag-suggestions" aria-label={t('existingTagSuggestions')}>
                {filteredTags.map(tag => <button type="button" key={tag.id} onClick={() => addSuggestedTag(tag.name)}>#{tag.name}</button>)}
              </div>
            )}
          </label>
          <label className="field prompt-field prompt-field-en">
            <span className="prompt-field-title">{t('englishPrompt')} <button type="button" className={`origin-marker ${originalLanguage === 'en' ? 'active' : ''}`} onClick={() => setOriginalLanguage('en')}>{originalLanguage === 'en' ? t('origin') : t('markAsOriginal')}</button></span>
            <textarea placeholder={t('englishPromptPlaceholder')} value={englishPrompt} onChange={e => setEnglishPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field prompt-field-zh-hant">
            <span className="prompt-field-title">{t('traditionalChinesePrompt')} <button type="button" className={`origin-marker ${originalLanguage === 'zh_hant' ? 'active' : ''}`} onClick={() => setOriginalLanguage('zh_hant')}>{originalLanguage === 'zh_hant' ? t('origin') : t('markAsOriginal')}</button></span>
            <textarea placeholder={t('traditionalPromptPlaceholder')} value={zhHantPrompt} onChange={e => setZhHantPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field prompt-field-zh-hans">
            <span className="prompt-field-title">{t('simplifiedChinesePrompt')} <button type="button" className={`origin-marker ${originalLanguage === 'zh_hans' ? 'active' : ''}`} onClick={() => setOriginalLanguage('zh_hans')}>{originalLanguage === 'zh_hans' ? t('origin') : t('markAsOriginal')}</button></span>
            <textarea placeholder={t('simplifiedPromptPlaceholder')} value={zhHansPrompt} onChange={e => setZhHansPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field notes-field">
            <span>{t('notes')}</span>
            <textarea placeholder={t('addNote')} value={notes} onChange={e => setNotes(e.target.value)} />
          </label>
          {persistedItem && imageDrafts.length > 0 && (
            <section className="item-image-manager" aria-labelledby="item-image-manager-title">
              <header>
                <span>
                  <strong id="item-image-manager-title">{t('itemImages')}</strong>
                  <small>{t('imageManagerHelp')}</small>
                </span>
                <b>{imageDrafts.length}</b>
              </header>
              <div className="item-image-manager-list">
                {imageDrafts.map((image, index) => {
                  const role = image.role || 'result_image';
                  const sameRole = imageDrafts.filter(candidate => (candidate.role || 'result_image') === role);
                  const roleIndex = sameRole.findIndex(candidate => candidate.id === image.id);
                  const isPrimary = image.id === primaryImageId;
                  return (
                    <article className={`item-image-manager-row${isPrimary ? ' is-primary' : ''}`} key={image.id}>
                      <div className="item-image-manager-preview">
                        <img src={mediaUrl(imageThumbnailPath(image) || image.original_path)} alt="" />
                        {isPrimary && <span><Star size={11} fill="currentColor" /> {t('primaryImage')}</span>}
                      </div>
                      <label>
                        <span>{t('imageRole')}</span>
                        <select value={role} onChange={event => updateImageRole(image.id, event.target.value as UploadImageRole)}>
                          <option value="result_image">{t('result')}</option>
                          <option value="reference_image">{t('reference')}</option>
                        </select>
                      </label>
                      <div className="item-image-manager-actions">
                        <button type="button" onClick={() => makePrimaryImage(image.id)} disabled={role === 'reference_image' || isPrimary} aria-label={t('setPrimaryImage')} title={t('setPrimaryImage')}><Star size={16} /></button>
                        <button type="button" onClick={() => moveImage(image.id, -1)} disabled={roleIndex <= 0} aria-label={t('moveImageEarlier')} title={t('moveImageEarlier')}><ChevronLeft size={17} /></button>
                        <button type="button" onClick={() => moveImage(image.id, 1)} disabled={roleIndex >= sameRole.length - 1} aria-label={t('moveImageLater')} title={t('moveImageLater')}><ChevronRight size={17} /></button>
                        <button type="button" className="remove" onClick={() => removeImage(image.id)} aria-label={t('removeImage')} title={t('removeImage')}><Trash2 size={16} /></button>
                      </div>
                      <span className="item-image-position">{index + 1}</span>
                    </article>
                  );
                })}
              </div>
            </section>
          )}
          <label className={`drop-zone result-drop-zone ${missingRequiredImage ? 'required' : ''}`}>
            <ImagePlus size={24} />
            <strong>{resultFile ? resultFile.name : hasExistingResultImage ? t('resultImageAlreadySaved') : t('resultImageRequired')}</strong>
            <span>{t('resultImageHelp')}</span>
            <input type="file" accept="image/*" required={!hasExistingResultImage} onChange={e => setResultFile(e.target.files?.[0])} />
          </label>
          <label className="drop-zone reference-drop-zone">
            <ImagePlus size={24} />
            <strong>{referenceFile ? referenceFile.name : t('referencePhotoOptional')}</strong>
            <span>{t('referencePhotoHelp')}</span>
            <input type="file" accept="image/*" onChange={e => setReferenceFile(e.target.files?.[0])} />
          </label>
        </div>

        {saveError && <p className="form-error" role="alert">{saveError}</p>}

        <div className="editor-actions">
          {allowDelete && persistedItem && <button className="danger" disabled={deleting || saving} onClick={deleteReference}><Trash2 size={16} /> {t('deleteReference')}</button>}
          <button className="secondary" disabled={deleting || saving} onClick={handleClose}>{t('cancel')}</button>
          <button className="primary" disabled={!title.trim() || !hasPrompt || missingRequiredImage || saving || deleting} onClick={save}>{saving ? t('saving') : t('saveReference')}</button>
        </div>
      </div>
    </div>
  );
}
