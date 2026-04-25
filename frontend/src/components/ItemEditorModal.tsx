import { useMemo, useState } from 'react';
import { ImagePlus, Trash2, X } from 'lucide-react';
import { api } from '../api/client';
import type { ClusterRecord, ItemDetail, TagRecord } from '../types';

function promptText(item: ItemDetail | undefined, language: string) {
  return item?.prompts.find(prompt => prompt.language === language)?.text || '';
}

function initialTraditionalPrompt(item: ItemDetail | undefined) {
  return promptText(item, 'zh_hant') || promptText(item, 'original');
}

export default function ItemEditorModal({
  item,
  clusters,
  tags: existingTags,
  onClose,
  onSaved,
  onDeleted,
}: {
  item?: ItemDetail;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [title, setTitle] = useState(item?.title || '');
  const [cluster, setCluster] = useState(item?.cluster?.name || '');
  const [tags, setTags] = useState(item?.tags.map(t => t.name).join(', ') || '');
  const [zhHantPrompt, setZhHantPrompt] = useState(initialTraditionalPrompt(item));
  const [zhHansPrompt, setZhHansPrompt] = useState(promptText(item, 'zh_hans'));
  const [englishPrompt, setEnglishPrompt] = useState(promptText(item, 'en'));
  const [resultFile, setResultFile] = useState<File>();
  const [referenceFile, setReferenceFile] = useState<File>();
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const hasExistingResultImage = Boolean(item?.images?.length);
  const hasPrompt = Boolean(zhHantPrompt.trim() || zhHansPrompt.trim() || englishPrompt.trim());
  const missingRequiredImage = !hasExistingResultImage && !resultFile;
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
    try {
      const prompts = [
        { language: 'zh_hant', text: zhHantPrompt.trim(), is_primary: true },
        { language: 'zh_hans', text: zhHansPrompt.trim(), is_primary: !zhHantPrompt.trim() },
        { language: 'en', text: englishPrompt.trim(), is_primary: !zhHantPrompt.trim() && !zhHansPrompt.trim() },
      ].filter(prompt => prompt.text);
      const payload = {
        title: title.trim(),
        cluster_name: cluster.trim() || undefined,
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        prompts,
      };
      const saved = item ? await api.updateItem(item.id, payload) : await api.createItem(payload);
      if (resultFile) await api.uploadImage(saved.id, resultFile, 'result_image');
      if (referenceFile) await api.uploadImage(saved.id, referenceFile, 'reference_image');
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const deleteReference = async () => {
    if (!item) return;
    if (!confirm('Delete this reference? It will be archived and hidden from the library.')) return;
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
        <button className="close" onClick={onClose} aria-label="Close">
          <X size={20} />
        </button>
        <div className="editor-head">
          <p className="modal-kicker">{item ? 'Update reference' : 'New reference'}</p>
          <h2>{item ? 'Edit prompt card' : 'Add prompt card'}</h2>
          <p>Keep the finished result image, collection, tags, and reusable multilingual prompts together.</p>
        </div>

        <div className="editor-grid">
          <label className="field field-title">
            <span>Title</span>
            <input placeholder="Give this reference a memorable name" value={title} onChange={e => setTitle(e.target.value)} />
          </label>
          <label className="field">
            <span>Collection</span>
            <input list="collection-suggestions" placeholder="e.g. 產品商業" value={cluster} onChange={e => setCluster(e.target.value)} />
            <datalist id="collection-suggestions">
              {filteredClusters.map(collection => <option key={collection.id} value={collection.name} />)}
            </datalist>
          </label>
          <label className="field tag-field">
            <span>Tags</span>
            <input list="tag-suggestions" placeholder="poster, product, cinematic" value={tags} onChange={e => setTags(e.target.value)} />
            <datalist id="tag-suggestions">
              {filteredTags.map(tag => <option key={tag.id} value={tag.name} />)}
            </datalist>
            {filteredTags.length > 0 && (
              <div className="tag-suggestions" aria-label="Existing tag suggestions">
                {filteredTags.map(tag => <button type="button" key={tag.id} onClick={() => addSuggestedTag(tag.name)}>#{tag.name}</button>)}
              </div>
            )}
          </label>
          <label className="field prompt-field">
            <span>Traditional Chinese prompt</span>
            <textarea placeholder="貼上繁體中文 prompt…" value={zhHantPrompt} onChange={e => setZhHantPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>Simplified Chinese prompt</span>
            <textarea placeholder="粘贴简体中文 prompt…" value={zhHansPrompt} onChange={e => setZhHansPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>English prompt</span>
            <textarea placeholder="Paste the English prompt…" value={englishPrompt} onChange={e => setEnglishPrompt(e.target.value)} />
          </label>
          <label className={`drop-zone ${missingRequiredImage ? 'required' : ''}`}>
            <ImagePlus size={24} />
            <strong>{resultFile ? resultFile.name : hasExistingResultImage ? 'Result image already saved' : 'Result image required'}</strong>
            <span>Required finished output image · PNG, JPG, WEBP or GIF</span>
            <input type="file" accept="image/*" required={!hasExistingResultImage} onChange={e => setResultFile(e.target.files?.[0])} />
          </label>
          <label className="drop-zone reference-drop-zone">
            <ImagePlus size={24} />
            <strong>{referenceFile ? referenceFile.name : 'Reference photo optional'}</strong>
            <span>Optional source/reference image for this prompt</span>
            <input type="file" accept="image/*" onChange={e => setReferenceFile(e.target.files?.[0])} />
          </label>
        </div>

        <div className="editor-actions">
          {item && <button className="danger" disabled={deleting || saving} onClick={deleteReference}><Trash2 size={16} /> Delete reference</button>}
          <button className="secondary" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!title.trim() || !hasPrompt || missingRequiredImage || saving || deleting} onClick={save}>{saving ? 'Saving…' : 'Save reference'}</button>
        </div>
      </div>
    </div>
  );
}
