import { useMemo, useState } from 'react';
import { ImagePlus, Trash2, X } from 'lucide-react';
import { api } from '../api/client';
import type { ClusterRecord, ItemDetail, TagRecord } from '../types';
import type { Translator } from '../utils/i18n';

function promptText(item: ItemDetail | undefined, language: string) {
  return item?.prompts.find(prompt => prompt.language === language)?.text || '';
}

function initialTraditionalPrompt(item: ItemDetail | undefined) {
  return promptText(item, 'zh_hant') || promptText(item, 'original');
}

export default function ItemEditorModal({
  item,
  t,
  clusters,
  tags: existingTags,
  onClose,
  onSaved,
  onDeleted,
}: {
  item?: ItemDetail;
  t: Translator;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
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
  const [resultFile, setResultFile] = useState<File>();
  const [referenceFile, setReferenceFile] = useState<File>();
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const hasExistingResultImage = Boolean(item?.images?.some(image => image.role === 'result_image'));
  const hasPrompt = Boolean(zhHantPrompt.trim() || zhHansPrompt.trim() || englishPrompt.trim());
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

  const save = async () => {
    if (!title.trim() || !hasPrompt || missingRequiredImage) return;
    setSaving(true);
    setSaveError('');
    try {
      const prompts = [
        { language: 'en', text: englishPrompt.trim(), is_primary: true },
        { language: 'zh_hant', text: zhHantPrompt.trim(), is_primary: !englishPrompt.trim() },
        { language: 'zh_hans', text: zhHansPrompt.trim(), is_primary: !englishPrompt.trim() && !zhHantPrompt.trim() },
      ].filter(prompt => prompt.text);
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
      const createdNewItem = !item;
      const saved = item ? await api.updateItem(item.id, payload) : await api.createItem(payload);
      try {
        if (resultFile) await api.uploadImage(saved.id, resultFile, 'result_image');
        if (referenceFile) await api.uploadImage(saved.id, referenceFile, 'reference_image');
      } catch (uploadError) {
        if (createdNewItem) await api.deleteItem(saved.id);
        throw uploadError;
      }
      onSaved();
      onClose();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t('saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const deleteReference = async () => {
    if (!item) return;
    if (!confirm(t('deleteReferenceConfirm'))) return;
    setDeleting(true);
    try {
      await api.deleteItem(item.id);
      onDeleted();
      onClose();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="editor modal polished-modal">
        <button className="close" onClick={onClose} aria-label={t('close')}>
          <X size={20} />
        </button>
        <div className="editor-head">
          <p className="modal-kicker">{item ? t('updateReference') : t('newReference')}</p>
          <h2>{item ? t('editPromptCard') : t('addPromptCard')}</h2>
          <p>{t('editorHelp')}</p>
        </div>

        <div className="editor-grid">
          <label className="field field-title">
            <span>{t('title')}</span>
            <input placeholder={t('titlePlaceholder')} value={title} onChange={e => setTitle(e.target.value)} />
          </label>
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
          <label className="field prompt-field">
            <span>{t('englishPrompt')}</span>
            <textarea placeholder={t('englishPromptPlaceholder')} value={englishPrompt} onChange={e => setEnglishPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>{t('traditionalChinesePrompt')}</span>
            <textarea placeholder={t('traditionalPromptPlaceholder')} value={zhHantPrompt} onChange={e => setZhHantPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>{t('simplifiedChinesePrompt')}</span>
            <textarea placeholder={t('simplifiedPromptPlaceholder')} value={zhHansPrompt} onChange={e => setZhHansPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>{t('notes')}</span>
            <textarea placeholder={t('addNote')} value={notes} onChange={e => setNotes(e.target.value)} />
          </label>
          <label className={`drop-zone ${missingRequiredImage ? 'required' : ''}`}>
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
          {item && <button className="danger" disabled={deleting || saving} onClick={deleteReference}><Trash2 size={16} /> {t('deleteReference')}</button>}
          <button className="secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="primary" disabled={!title.trim() || !hasPrompt || missingRequiredImage || saving || deleting} onClick={save}>{saving ? t('saving') : t('saveReference')}</button>
        </div>
      </div>
    </div>
  );
}
