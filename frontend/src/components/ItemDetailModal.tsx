import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { Check, Copy, Download, ExternalLink, Heart, Maximize2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import { focusFirstAvailable } from '../hooks/useModalFocus';
import type { ClusterRecord, ImageRecord, ItemDetail, PromptRecord, TagRecord, UiLanguage } from '../types';
import { copyTextToClipboard } from '../utils/clipboard';
import { localizedDemoTitle } from '../utils/demoTitles';
import { downloadFileName, imageDisplayPath, imageHeroPath, imageOriginalPath, imageThumbnailPath, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';
import { PROMPT_LANGUAGE_LABELS, resolveOriginalPrompt, resolvePromptText, type PromptCopyLanguage, type PromptLanguage } from '../utils/prompts';

const LANG_LABELS: Record<string, string> = {
  ...PROMPT_LANGUAGE_LABELS,
  en: 'ENG',
};
const promptDisplayOrder = ['en', 'zh_hant', 'zh_hans'];
const FOCUSABLE_SELECTOR = 'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

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

function isReferenceImage(image?: ImageRecord) {
  return image?.role === 'reference_image';
}

function generationProviderLabel(provider?: string | null) {
  if (!provider || provider === 'manual_upload') return '';
  if (provider === 'openai_codex_oauth_native') return 'ChatGPT / Codex';
  if (provider === 'xai' || provider === 'xai_api') return 'xAI';
  return provider.replace(/[_-]+/g, ' ').replace(/\b\w/g, character => character.toUpperCase());
}

function generationSourceLabel(image?: ImageRecord) {
  if (!image) return '';
  return [generationProviderLabel(image.generation_provider), image.generation_model]
    .filter((value, index, values) => value && values.indexOf(value) === index)
    .join(' · ');
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


function resolveInitialPromptLanguage(prompts: PromptRecord[], preferredLanguage: PromptCopyLanguage): PromptLanguage {
  if (preferredLanguage === 'origin') {
    const originalLanguage = resolveOriginalPrompt(prompts)?.language;
    if (originalLanguage === 'en' || originalLanguage === 'zh_hant' || originalLanguage === 'zh_hans') return originalLanguage;
    return 'en';
  }
  return preferredLanguage;
}

function InlineEditableField({
  t,
  className,
  value,
  placeholder,
  inputList,
  onCommit,
  editable = true,
  children,
}: {
  t: Translator;
  className: string;
  value: string;
  placeholder?: string;
  inputList?: string;
  onCommit: (value: string) => void;
  editable?: boolean;
  children?: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = () => { onCommit(draft); setEditing(false); };
  const cancel = () => { setDraft(value); setEditing(false); };
  if (editing && editable) {
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
          <button type="button" className="inline-edit-confirm" onClick={confirm} aria-label={t('confirmEdit')}><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} aria-label={t('cancelEdit')}><X size={14} /></button>
        </span>
      </span>
    );
  }
  if (!editable) {
    return <span className={`inline-editable ${className} is-read-only`}>{value || placeholder}</span>;
  }
  return (
    <span className={`inline-editable ${className}`} onDoubleClick={() => setEditing(true)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') setEditing(true); }}>
      {value || placeholder}
    </span>
  );
}

function InlineEditableTextArea({
  t,
  className,
  value,
  placeholder,
  onCommit,
  editable = true,
}: {
  t: Translator;
  className: string;
  value: string;
  placeholder?: string;
  onCommit: (value: string) => void;
  editable?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = () => { onCommit(draft); setEditing(false); };
  const cancel = () => { setDraft(value); setEditing(false); };
  if (editing && editable) {
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
          <button type="button" className="inline-edit-confirm" onClick={confirm} aria-label={t('confirmEdit')}><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} aria-label={t('cancelEdit')}><X size={14} /></button>
        </span>
      </div>
    );
  }
  if (!editable) {
    return <div className={`inline-editable ${className} is-read-only ${value ? '' : 'notes-empty'}`}>{value ? <p>{value}</p> : <span className="add-note-affordance">{placeholder}</span>}</div>;
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
  uiLanguage,
  preferredLanguage,
  clusters,
  tags,
  onClose,
  onCopyPrompt,
  onEdit,
  onChanged,
  onDelete,
  onOpenItem,
  onGenerate,
  showMutations = true,
  showManagementActions = true,
  canGenerate = false,
}: {
  id?: string;
  t: Translator;
  uiLanguage: UiLanguage;
  preferredLanguage: PromptCopyLanguage;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  onClose: () => void;
  onCopyPrompt: (success: boolean) => void;
  onEdit: (item: ItemDetail) => void;
  onChanged: () => void;
  onDelete?: (item: ItemDetail) => void | Promise<void>;
  onOpenItem?: (id: string) => void;
  onGenerate: (item: ItemDetail) => void;
  showMutations?: boolean;
  showManagementActions?: boolean;
  canGenerate?: boolean;
}) {
  const allowManagementActions = showMutations && showManagementActions;
  const [item, setItem] = useState<ItemDetail>();
  const [loadError, setLoadError] = useState<string>();
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [lang, setLang] = useState<string>(preferredLanguage);
  const [addingTag, setAddingTag] = useState(false);
  const [inlineMutationBusy, setInlineMutationBusy] = useState(false);
  const inlineMutationBusyRef = useRef(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [tagQuery, setTagQuery] = useState('');
  const [editingPromptLanguage, setEditingPromptLanguage] = useState<string>();
  const [promptDraft, setPromptDraft] = useState('');
  const [selectedImageId, setSelectedImageId] = useState<string>();
  const [isClosing, setIsClosing] = useState(false);
  const [isHeroFullscreen, setIsHeroFullscreen] = useState(false);
  const lastDefaultPromptKeyRef = useRef('');
  const heroImageRef = useRef<HTMLImageElement | null>(null);
  const heroFullscreenFrameRef = useRef<HTMLDivElement | null>(null);
  const heroFullscreenTriggerRef = useRef<HTMLButtonElement | null>(null);
  const heroFullscreenCloseRef = useRef<HTMLButtonElement | null>(null);
  const heroFullscreenWasOpenRef = useRef(false);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const modalRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  const handleClose = () => {
    if (isClosing) return;
    setIsClosing(true);
    const opener = openerRef.current;
    const delay = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 180;
    window.setTimeout(() => {
      onClose();
      window.setTimeout(() => {
        const fallbacks = Array.from(document.querySelectorAll<HTMLElement>('[data-card-id]'))
          .filter(element => element.getAttribute('data-card-id') === id);
        const searchFallback = document.querySelector<HTMLElement>('.toolbar-search input');
        focusFirstAvailable([opener, ...fallbacks, searchFallback]);
      }, 0);
    }, delay);
  };

  const closeHeroFullscreen = async () => {
    if (document.fullscreenElement === heroFullscreenFrameRef.current) {
      await document.exitFullscreen?.();
    }
    setIsHeroFullscreen(false);
  };

  const toggleHeroFullscreen = async () => {
    if (document.fullscreenElement === heroFullscreenFrameRef.current || isHeroFullscreen) {
      await closeHeroFullscreen();
      return;
    }
    if (!heroFullscreenFrameRef.current) return;
    try {
      if (heroFullscreenFrameRef.current.requestFullscreen) {
        await heroFullscreenFrameRef.current.requestFullscreen();
      } else {
        setIsHeroFullscreen(true);
      }
    } catch {
      setIsHeroFullscreen(true);
    }
  };

  useEffect(() => { setLang(preferredLanguage); }, [preferredLanguage, id]);
  useEffect(() => { if (id) setIsClosing(false); }, [id]);

  useEffect(() => {
    if (!id) return undefined;
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement && !backdropRef.current?.contains(activeElement)) {
      openerRef.current = activeElement;
    }
    const timer = window.setTimeout(() => {
      modalRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [id]);

  useEffect(() => {
    if (!id) return undefined;
    let cancelled = false;
    setItem(undefined);
    setLoadError(undefined);
    api.item(id)
      .then(nextItem => { if (!cancelled) setItem(nextItem); })
      .catch(error => { if (!cancelled) setLoadError(error instanceof Error ? error.message : t('loadFailed')); });
    return () => { cancelled = true; };
  }, [id, loadAttempt, t]);

  useEffect(() => {
    const syncHeroFullscreenState = () => setIsHeroFullscreen(document.fullscreenElement === heroFullscreenFrameRef.current);
    document.addEventListener('fullscreenchange', syncHeroFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncHeroFullscreenState);
  }, []);

  useEffect(() => {
    let focusTarget: HTMLElement | null = null;
    if (isHeroFullscreen) {
      heroFullscreenWasOpenRef.current = true;
      focusTarget = heroFullscreenCloseRef.current;
    } else if (heroFullscreenWasOpenRef.current) {
      heroFullscreenWasOpenRef.current = false;
      focusTarget = heroFullscreenTriggerRef.current;
    }
    if (!focusTarget) return undefined;
    const frame = window.requestAnimationFrame(() => focusTarget?.focus({ preventScroll: true }));
    return () => window.cancelAnimationFrame(frame);
  }, [isHeroFullscreen]);

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
    const initialLanguage = resolveInitialPromptLanguage(item.prompts, preferredLanguage);
    const nextPrompt = resolvePromptRecord(availablePromptRecords, initialLanguage, initialLanguage);
    if (nextPrompt) setLang(nextPrompt.language);
    lastDefaultPromptKeyRef.current = defaultPromptKey;
  }, [item, availablePromptRecords, preferredLanguage, id]);

  const uniqueImages = dedupeImages(item?.images || []);
  const primaryImage = selectPrimaryImage(uniqueImages);
  const selectedImage = uniqueImages.find(image => image.id === selectedImageId) || primaryImage;
  const selectedImageGenerationSource = generationSourceLabel(selectedImage);
  const selectedImageIndex = selectedImage ? uniqueImages.findIndex(image => image.id === selectedImage.id) : -1;
  const heroStyle = selectedImage?.width && selectedImage.height
    ? ({ '--detail-image-aspect-ratio': `${selectedImage.width} / ${selectedImage.height}` } as CSSProperties)
    : undefined;
  useEffect(() => {
    if (!item || uniqueImages.length === 0) {
      setSelectedImageId(undefined);
      return;
    }
    if (!selectedImageId || !uniqueImages.some(image => image.id === selectedImageId)) {
      setSelectedImageId(primaryImage?.id || uniqueImages[0]?.id);
    }
  }, [item?.id, uniqueImages.length, primaryImage?.id, selectedImageId]);

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
  const displayTitle = item ? localizedDemoTitle(item, uiLanguage) : '';
  const originalPrompt = resolveOriginalPrompt(item?.prompts);
  const fallbackLanguage = preferredLanguage === 'origin' ? resolveInitialPromptLanguage(item?.prompts || [], preferredLanguage) : preferredLanguage;
  const resolvedPrompt = resolvePromptRecord(availablePromptRecords, lang, fallbackLanguage);
  const copyText = prompt?.text || resolvedPrompt?.text || resolvePromptText(item?.prompts, preferredLanguage, displayTitle || item?.title || '');
  const toggleFavorite = () => {
    if (!item) return;
    api.favorite(item.id).then(updated => { setItem(updated); onChanged(); });
  };
  const commitInlineUpdate = async (payload: Record<string, unknown>) => {
    if (!item || inlineMutationBusyRef.current) return;
    inlineMutationBusyRef.current = true;
    setInlineMutationBusy(true);
    try {
      const updated = await api.updateItem(item.id, payload);
      setItem(updated);
      onChanged();
    } finally {
      inlineMutationBusyRef.current = false;
      setInlineMutationBusy(false);
    }
  };
  const handleDelete = async () => {
    if (!item || deleteBusy) return;
    setDeleteBusy(true);
    try {
      await onDelete?.(item);
    } finally {
      setDeleteBusy(false);
    }
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

  const focusableModalElements = () => {
    if (!backdropRef.current) return [];
    return Array.from(backdropRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter(element => !element.hasAttribute('disabled') && (element.getClientRects().length > 0 || element === document.activeElement));
  };

  const handleModalKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      const target = event.target as HTMLElement | null;
      if (isHeroFullscreen) {
        event.preventDefault();
        void closeHeroFullscreen();
        return;
      }
      if (target?.closest('.inline-editable.is-editing, .prompt-edit-textarea, .tag-add-popover')) return;
      event.preventDefault();
      handleClose();
      return;
    }

    if (event.key !== 'Tab') return;
    const focusable = focusableModalElements();
    if (focusable.length === 0) {
      event.preventDefault();
      modalRef.current?.focus({ preventScroll: true });
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const activeElement = document.activeElement as HTMLElement | null;
    if (!activeElement || !backdropRef.current?.contains(activeElement)) {
      event.preventDefault();
      first.focus({ preventScroll: true });
      return;
    }
    if (event.shiftKey && activeElement === first) {
      event.preventDefault();
      last.focus({ preventScroll: true });
    } else if (!event.shiftKey && activeElement === last) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    }
  };

  return (
    <div ref={backdropRef} className={`modal-backdrop${isClosing ? ' is-closing' : ''}`} onClick={handleClose} onKeyDown={handleModalKeyDown}>
      <div
        ref={modalRef}
        className="detail modal polished-modal"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={displayTitle || item?.title || t('loading')}
        tabIndex={-1}
      >
        {!item ? (
          loadError ? (
            <div className="modal-load-error" role="alert">
              <p>{loadError}</p>
              <button type="button" className="secondary" onClick={() => setLoadAttempt(attempt => attempt + 1)}>{t('retry')}</button>
            </div>
          ) : <p className="modal-loading" role="status">{t('loading')}</p>
        ) : (
          <div className="detail-modal-content">
            <div className="detail-layout">
              <section
                className={`modal-hero${uniqueImages.length === 1 ? ' has-single-hero' : ''}${isHeroFullscreen ? ' is-mobile-fullscreen' : ''}`}
                style={heroStyle}
              >
                {selectedImage ? (
                  <>
                    <div ref={heroFullscreenFrameRef} className={`detail-fullscreen-frame${isHeroFullscreen ? ' is-mobile-fullscreen' : ''}`}>
                      <img
                        ref={heroImageRef}
                        className="hero-image"
                        src={mediaUrl(isHeroFullscreen ? imageOriginalPath(selectedImage) : imageHeroPath(selectedImage))}
                        alt={displayTitle || item.title}
                      />
                       <button ref={heroFullscreenCloseRef} className="modal-icon-button detail-fullscreen-close" type="button" onClick={closeHeroFullscreen} aria-label={t('closeFullscreen')}><X size={20} strokeWidth={2.25} /></button>
                    </div>
                    {uniqueImages.length > 1 && <span className="image-counter">{selectedImageIndex + 1} / {uniqueImages.length}</span>}
                     {isReferenceImage(selectedImage) && <span className="image-role-badge">{t('reference')}</span>}
                     <button ref={heroFullscreenTriggerRef} className="modal-icon-button detail-fullscreen-overlay" type="button" onClick={toggleHeroFullscreen} aria-label={t('viewFullscreen')} title={t('viewFullscreen')}>
                      <Maximize2 size={20} strokeWidth={2.25} />
                    </button>
                  </>
                ) : (
                  <div className="placeholder hero-image">{t('noImage')}</div>
                )}
                <div className="mobile-hero-actions" aria-label={t('itemActions')}>
                  <button className="modal-icon-button mobile-hero-close" onClick={handleClose} aria-label={t('close')}>
                    <X size={20} strokeWidth={2.25} />
                  </button>
                  {(selectedImage || showMutations) && (
                    <span className="mobile-hero-primary-actions">
                       {selectedImage && <a className="modal-icon-button download-button" href={mediaUrl(selectedImage.original_path || imageHeroPath(selectedImage))} download={downloadFileName(displayTitle || item.title, selectedImage?.original_path || imageHeroPath(selectedImage))} aria-label={t('download')} title={t('download')}><Download size={18} /></a>}
                      {allowManagementActions && <button className="modal-icon-button favorite-button" onClick={toggleFavorite} aria-label={item.favorite ? t('saved') : t('favorite')}>
                        <Heart size={18} fill={item.favorite ? 'currentColor' : 'none'} />
                      </button>}
                      {showMutations && <button className="modal-icon-button edit-button" onClick={() => onEdit(item)} aria-label={t('edit')}>
                        <Pencil size={18} />
                      </button>}
                      {allowManagementActions && <button className="modal-icon-button detail-delete-button" onClick={handleDelete} disabled={deleteBusy} aria-label={t('deleteReference')} title={t('deleteReference')}>
                        <Trash2 size={18} />
                      </button>}
                       {showMutations && canGenerate && <button className="modal-icon-button mobile-generate-variant-button" onClick={() => onGenerate(item)} aria-label={t('generateVariant')} title={t('generateVariant')}>
                         <Plus size={18} />
                         <span className="mobile-generate-variant-label">{t('generate')}</span>
                      </button>}
                    </span>
                  )}
                </div>
                {uniqueImages.length > 1 && (
                   <div className="rail glass-rail image-gallery-rail" aria-label={t('itemImages')}>
                    {uniqueImages.map((img, index) => (
                      <button
                        type="button"
                        key={getImageIdentity(img)}
                        className={`image-gallery-thumb ${selectedImage?.id === img.id ? 'active' : ''}`}
                        onClick={() => setSelectedImageId(img.id)}
                         aria-label={`${t('showImage')} ${index + 1} / ${uniqueImages.length}`}
                        aria-pressed={selectedImage?.id === img.id}
                      >
                        <img src={mediaUrl(imageDisplayPath(img) || imageThumbnailPath(img))} alt="" loading="lazy" decoding="async" />
                         {isReferenceImage(img) && <span className="image-thumb-role-badge">{t('reference')}</span>}
                      </button>
                    ))}
                  </div>
                )}
              </section>

              <aside className="detail-side">
                <div className="detail-side-actions">
                  <span className="detail-side-primary-actions">
                     {showMutations && canGenerate && <button className="secondary generate-variant-button" onClick={() => onGenerate(item)} aria-label={t('generateVariant')} title={t('generateVariant')}>{t('generate')}</button>}
                     {selectedImage && <a className="modal-icon-button download-button" href={mediaUrl(selectedImage.original_path || imageHeroPath(selectedImage))} download={downloadFileName(displayTitle || item.title, selectedImage?.original_path || imageHeroPath(selectedImage))} aria-label={t('download')} title={t('download')}><Download size={18} /></a>}
                    {allowManagementActions && <button className="modal-icon-button favorite-button" onClick={toggleFavorite} aria-label={item.favorite ? t('saved') : t('favorite')}>
                      <Heart size={18} fill={item.favorite ? 'currentColor' : 'none'} />
                    </button>}
                    {showMutations && <button className="modal-icon-button edit-button" onClick={() => onEdit(item)} aria-label={t('edit')}>
                      <Pencil size={18} />
                    </button>}
                    {allowManagementActions && <button className="modal-icon-button detail-delete-button" onClick={handleDelete} disabled={deleteBusy} aria-label={t('deleteReference')} title={t('deleteReference')}>
                      <Trash2 size={18} />
                    </button>}
                  </span>
                  <button className="modal-icon-button close" onClick={handleClose} aria-label={t('close')}>
                    <X size={20} strokeWidth={2.25} />
                  </button>
                </div>
                <InlineEditableField t={t} className="collection-inline-edit" value={item.cluster?.name || ''} placeholder={t('unclustered')} inputList="detail-collection-suggestions" onCommit={value => commitInlineUpdate({ cluster_name: value.trim() || null })} editable={allowManagementActions && !inlineMutationBusy}>
                  <datalist id="detail-collection-suggestions">
                    {clusters.map(collection => <option key={collection.id} value={collection.name} />)}
                  </datalist>
                </InlineEditableField>
                <h2>
                  <InlineEditableField t={t} className="title-inline-edit" value={showMutations ? item.title : (displayTitle || item.title)} placeholder={t('titlePlaceholder')} onCommit={value => commitInlineUpdate({ title: value.trim() || item.title })} editable={allowManagementActions && !inlineMutationBusy} />
                </h2>
                <p className="muted metadata-row">
                  <InlineEditableField t={t} className="metadata-inline-edit" value={item.model || t('defaultModel')} placeholder={t('imageGeneratedFrom')} onCommit={value => commitInlineUpdate({ model: value.trim() || item.model })} editable={allowManagementActions && !inlineMutationBusy} />
                  <span>·</span>
                  <InlineEditableField t={t} className="metadata-inline-edit" value={`@${item.author || 'User'}`} placeholder="@User" onCommit={value => commitInlineUpdate({ author: value.replace(/^@/, '').trim() || 'User' })} editable={allowManagementActions && !inlineMutationBusy} />
                  {item.source_url && (
                    <a className="source-icon-link" href={item.source_url} target="_blank" rel="noreferrer" aria-label={t('source')}>
                      <ExternalLink size={16} />
                    </a>
                  )}
                </p>
                {selectedImageGenerationSource && (
                  <p className="image-generation-provenance">
                    <span>{t('generatedWith')}</span>
                    <strong>{selectedImageGenerationSource}</strong>
                  </p>
                )}

                <div className="prompt-blocks" aria-label={t('promptLanguage')}>
                  {(() => {
                    return (
                      <section className="prompt-block prompt-panel active">
                        <header className="prompt-block-header">
                          <div className="prompt-language-tabs tabs" role="tablist" aria-label={t('promptLanguage')}>
                            {promptDisplayOrder.map(promptLanguage => {
                              const tabPrompt = item.prompts.find(prompt => prompt.language === promptLanguage);
                              const isOriginalPrompt = Boolean(tabPrompt?.is_original || originalPrompt?.language === promptLanguage);
                              return (
                                <button
                                  type="button"
                                  role="tab"
                                  aria-selected={lang === promptLanguage}
                                  className={`prompt-language-tab ${lang === promptLanguage ? 'active' : ''} ${isOriginalPrompt ? 'is-original' : ''}`}
                                  onClick={() => { setLang(promptLanguage); cancelPromptEdit(); }}
                                  title={tabPrompt?.text.trim() ? undefined : t('promptText')}
                                  key={promptLanguage}
                                >
                                  {LANG_LABELS[promptLanguage] || promptLanguage}
                                  {isOriginalPrompt && <span className="origin-badge">{t('origin')}</span>}
                                </button>
                              );
                            })}
                          </div>
                          <span className="prompt-block-actions">
                            <button type="button" className="prompt-copy-icon" onClick={() => handleCopyPrompt(prompt?.text || '')} aria-label={t('copyPrompt')} disabled={!prompt?.text}>
                              <Copy size={15} />
                            </button>
                            {allowManagementActions && <button type="button" className="prompt-edit-icon" onClick={() => startPromptEdit(lang, prompt?.text || '')} aria-label={t('edit')}>
                              <Pencil size={15} />
                            </button>}
                          </span>
                        </header>
                        <div className="prompt-panel-body">
                          {allowManagementActions && editingPromptLanguage === lang ? (
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
                                 <button type="button" className="inline-edit-confirm" onClick={confirmPromptEdit} aria-label={t('confirmEdit')}><Check size={14} /></button>
                                 <button type="button" className="inline-edit-cancel" onClick={cancelPromptEdit} aria-label={t('cancelEdit')}><X size={14} /></button>
                              </span>
                            </>
                          ) : (
                            <div className={`prompt-inline-edit ${prompt?.text ? '' : 'notes-empty'} ${allowManagementActions ? '' : 'is-read-only'}`} onDoubleClick={() => { if (allowManagementActions) startPromptEdit(lang, prompt?.text || ''); }} tabIndex={allowManagementActions ? 0 : undefined} onKeyDown={event => { if (allowManagementActions && event.key === 'Enter') startPromptEdit(lang, prompt?.text || ''); }}>
                              {prompt?.text ? <p>{prompt.text}</p> : <span className="add-note-affordance">{t('promptText')}</span>}
                            </div>
                          )}
                        </div>
                      </section>
                    );
                  })()}
                </div>

                <InlineEditableTextArea t={t} className="notes-inline-edit" value={item.notes || ''} placeholder={t('addNote')} onCommit={value => commitInlineUpdate({ notes: value.trim() || null })} editable={allowManagementActions && !inlineMutationBusy} />

                <div className="tags detail-tags">
                  {item.tags.map(tag => (
                     <span className="detail-tag-chip" key={tag.id}>#{tag.name}{allowManagementActions && <button type="button" className="tag-unlink-button" onClick={() => unlinkTag(tag.name)} aria-label={t('removeTag').replace('${tag}', tag.name)}><X size={12} /></button>}</span>
                  ))}
                  {allowManagementActions && (addingTag ? (
                    <span className="tag-add-popover">
                      <input className="tag-add-input" autoFocus value={tagQuery} onChange={event => setTagQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') addTag(tagQuery); if (event.key === 'Escape') setAddingTag(false); }} placeholder={t('tags')} />
                      <button type="button" className="inline-edit-confirm" onClick={() => addTag(tagQuery)}><Check size={12} /></button>
                      <button type="button" className="inline-edit-cancel" onClick={() => setAddingTag(false)}><X size={12} /></button>
                      {filteredTagSuggestions.length > 0 && <span className="tag-add-suggestions">{filteredTagSuggestions.map(tag => <button type="button" key={tag.id} onClick={() => addTag(tag.name)}>#{tag.name}</button>)}</span>}
                    </span>
                  ) : (
                    <button type="button" className="add-tag-chip" onClick={() => setAddingTag(true)} aria-label={t('tags')}><Plus size={14} /></button>
                  ))}
                </div>
              </aside>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
