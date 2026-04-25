import { useState } from 'react';
import { ImagePlus, X } from 'lucide-react';
import { api } from '../api/client';
import type { ItemDetail } from '../types';

export default function ItemEditorModal({
  item,
  onClose,
  onSaved,
}: {
  item?: ItemDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(item?.title || '');
  const [cluster, setCluster] = useState(item?.cluster?.name || '');
  const [tags, setTags] = useState(item?.tags.map(t => t.name).join(', ') || '');
  const [prompt, setPrompt] = useState(item?.prompts[0]?.text || '');
  const [file, setFile] = useState<File>();

  const save = async () => {
    const payload = {
      title,
      cluster_name: cluster,
      tags: tags.split(',').map(t => t.trim()).filter(Boolean),
      prompts: [{ language: 'original', text: prompt, is_primary: true }],
    };
    const saved = item ? await api.updateItem(item.id, payload) : await api.createItem(payload);
    if (file) await api.uploadImage(saved.id, file);
    onSaved();
    onClose();
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
          <p>Keep the finished image, collection, tags, and reusable prompt together.</p>
        </div>

        <div className="editor-grid">
          <label className="field field-title">
            <span>Title</span>
            <input placeholder="Give this reference a memorable name" value={title} onChange={e => setTitle(e.target.value)} />
          </label>
          <label className="field">
            <span>Collection</span>
            <input placeholder="e.g. 產品商業" value={cluster} onChange={e => setCluster(e.target.value)} />
          </label>
          <label className="field">
            <span>Tags</span>
            <input placeholder="poster, product, cinematic" value={tags} onChange={e => setTags(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>Prompt</span>
            <textarea placeholder="Paste the prompt here…" value={prompt} onChange={e => setPrompt(e.target.value)} />
          </label>
          <label className="drop-zone">
            <ImagePlus size={24} />
            <strong>{file ? file.name : 'Drop or choose image'}</strong>
            <span>PNG, JPG, WEBP or GIF</span>
            <input type="file" accept="image/*" onChange={e => setFile(e.target.files?.[0])} />
          </label>
        </div>

        <div className="editor-actions">
          <button className="secondary" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!title || !prompt} onClick={save}>Save reference</button>
        </div>
      </div>
    </div>
  );
}
