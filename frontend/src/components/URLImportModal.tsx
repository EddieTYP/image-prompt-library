import { useState } from 'react';
import { Link2, X } from 'lucide-react';
import { api } from '../api/client';
import type { ClusterRecord, ImportDraftCreate, ItemDetail } from '../types';

export default function URLImportModal({ clusters, onClose, onImported }: {
  clusters: ClusterRecord[];
  onClose: () => void;
  onImported: (item: ItemDetail) => void;
}) {
  const [url, setUrl] = useState('');
  const [draft, setDraft] = useState<ImportDraftCreate>();
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [promptText, setPromptText] = useState('');
  const [cluster, setCluster] = useState('');
  const [tags, setTags] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const preview = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await api.previewImportUrl(url.trim());
      setDraft(result);
      setTitle(result.title);
      setAuthor(result.author || '');
      setPromptText(result.prompts.find(prompt => prompt.is_primary)?.text || result.prompts[0]?.text || '');
      setCluster(result.suggested_cluster_name || '');
      setTags(result.suggested_tags.join(', '));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not preview this URL.');
    } finally {
      setBusy(false);
    }
  };

  const accept = async () => {
    if (!draft) return;
    setBusy(true);
    setError('');
    try {
      const payload: ImportDraftCreate = {
        ...draft,
        title: title.trim(),
        author: author.trim() || undefined,
        suggested_cluster_name: cluster.trim() || undefined,
        suggested_tags: tags.split(',').map(tag => tag.trim()).filter(Boolean),
        prompts: [{ language: 'original', text: promptText.trim(), is_primary: true, is_original: true }],
        media: [],
      };
      const staged = await api.createImportDraft(payload);
      if (staged.status === 'duplicate') throw new Error('This source or prompt already exists in the library.');
      const result = await api.acceptImportDraft(staged.id);
      onImported(result.item);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Import failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="url-import-title">
      <div className="modal editor url-import-modal">
        <button type="button" className="close" onClick={onClose} aria-label="Close"><X /></button>
        <div className="editor-head">
          <p className="modal-kicker">URL import</p>
          <h2 id="url-import-title">Import a prompt from the web</h2>
          <p>Preview metadata first. Nothing is saved until you confirm.</p>
        </div>
        <div className="editor-grid">
          <label className="field field-title">
            <span>Public URL</span>
            <div className="url-import-row"><input type="url" value={url} onChange={event => setUrl(event.target.value)} placeholder="https://x.com/... or https://www.threads.net/..." disabled={busy} /><button type="button" className="secondary" onClick={preview} disabled={busy || !url.trim()}>{busy && !draft ? 'Loading...' : 'Preview'}</button></div>
          </label>
          {draft && <>
            <label className="field field-title"><span>Title</span><input value={title} onChange={event => setTitle(event.target.value)} /></label>
            <label className="field"><span>Author</span><input value={author} onChange={event => setAuthor(event.target.value)} /></label>
            <label className="field"><span>Collection</span><input list="url-import-clusters" value={cluster} onChange={event => setCluster(event.target.value)} /><datalist id="url-import-clusters">{clusters.map(item => <option key={item.id} value={item.name} />)}</datalist></label>
            <label className="field field-title"><span>Tags</span><input value={tags} onChange={event => setTags(event.target.value)} placeholder="poster, cinematic" /></label>
            <label className="field prompt-field"><span>Original prompt</span><textarea value={promptText} onChange={event => setPromptText(event.target.value)} placeholder="Paste the prompt manually if the page did not expose it." /></label>
            {draft.warnings.length > 0 && <div className="url-import-warnings" role="status">{draft.warnings.map(warning => <p key={warning}>{warning}</p>)}</div>}
          </>}
        </div>
        {error && <p className="form-error url-import-error" role="alert">{error}</p>}
        <div className="editor-actions">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="primary" onClick={accept} disabled={!draft || !title.trim() || !promptText.trim() || busy}><Link2 size={16} /> {busy && draft ? 'Importing...' : 'Confirm import'}</button>
        </div>
      </div>
    </div>
  );
}
