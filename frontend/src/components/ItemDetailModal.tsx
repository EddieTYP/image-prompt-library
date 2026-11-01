import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { ArrowRight, Check, Copy, Download, ExternalLink, Heart, Maximize2, MoreHorizontal, Pencil, Plus, Trash2, WandSparkles, X } from 'lucide-react';
import { api, mediaUrl } from '../api/client';
import { focusFirstAvailable } from '../hooks/useModalFocus';
import type { ClusterRecord, GenerationDraftContext, ImageRecord, ItemDetail, PromptRecord, TagRecord, UiLanguage } from '../types';
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
const imageEditIcon = <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 9V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4M3 16l5-5 3 3" /><path d="m12 21 1-4 6-6 3 3-6 6-4 1Zm5-8 3 3" /></svg>;
const imageGenerateIcon = <WandSparkles size={20} strokeWidth={1.75} aria-hidden="true" />;
const FOCUSABLE_SELECTOR = 'a[href],button:not(:disabled),textarea:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex]:not([tabindex="-1"])';

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
  if (provider === 'xai' || provider === 'xai_grok_oauth') return 'Grok';
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
  busy = false,
  children,
}: {
  t: Translator;
  className: string;
  value: string;
  placeholder?: string;
  inputList?: string;
  onCommit: (value: string) => Promise<boolean>;
  editable?: boolean;
  busy?: boolean;
  children?: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = async () => { if (!busy && await onCommit(draft)) setEditing(false); };
  const cancel = () => { if (busy) return; setDraft(value); setEditing(false); };
  if (editing && editable) {
    return (
      <span className={`inline-editable ${className} is-editing`}>
        <input
          value={draft}
          disabled={busy}
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
          <button type="button" className="inline-edit-confirm" onClick={confirm} disabled={busy} aria-label={t('confirmEdit')}><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} disabled={busy} aria-label={t('cancelEdit')}><X size={14} /></button>
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
  busy = false,
}: {
  t: Translator;
  className: string;
  value: string;
  placeholder?: string;
  onCommit: (value: string) => Promise<boolean>;
  editable?: boolean;
  busy?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = async () => { if (!busy && await onCommit(draft)) setEditing(false); };
  const cancel = () => { if (busy) return; setDraft(value); setEditing(false); };
  if (editing && editable) {
    return (
      <div className={`inline-editable ${className} is-editing`}>
        <textarea
          value={draft}
          disabled={busy}
          placeholder={placeholder}
          autoFocus
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') confirm();
            if (event.key === 'Escape') cancel();
          }}
        />
        <span className="inline-edit-controls">
          <button type="button" className="inline-edit-confirm" onClick={confirm} disabled={busy} aria-label={t('confirmEdit')}><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} disabled={busy} aria-label={t('cancelEdit')}><X size={14} /></button>
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
  onGenerationHistory,
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
  onGenerate: (item: ItemDetail, draft: GenerationDraftContext) => void;
  onGenerationHistory: (item: ItemDetail, jobId: string) => void;
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
  const [inlineMutationError, setInlineMutationError] = useState<string>();
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
  const hasDistinctGenerationPrompt = Boolean(selectedImage?.generation_prompt_text?.trim() && !item?.prompts.some(entry => entry.text.trim() === selectedImage.generation_prompt_text!.trim()));
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
  const generateFromSelection = (withImage: boolean) => {
    if (!item || editingPromptLanguage !== undefined || inlineMutationBusy) return;
    onGenerate(item, {
      promptText: copyText,
      promptLanguage: prompt?.text ? prompt.language : (resolvedPrompt?.language || originalPrompt?.language || 'en'),
      referenceImage: withImage ? selectedImage : undefined,
    });
  };
  const toggleFavorite = () => {
    if (!item) return;
    api.favorite(item.id).then(updated => { setItem(updated); onChanged(); });
  };
  const commitInlineUpdate = async (payload: Record<string, unknown>) => {
    if (!item || inlineMutationBusyRef.current) return false;
    inlineMutationBusyRef.current = true;
    setInlineMutationBusy(true);
    setInlineMutationError(undefined);
    try {
      const updated = await api.updateItem(item.id, payload);
      setItem(updated);
      onChanged();
      return true;
    } catch (error) {
      setInlineMutationError(error instanceof Error ? error.message : t('saveFailed'));
      return false;
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
    return commitInlineUpdate({ prompts });
  };
  const startPromptEdit = (language: string, text: string) => {
    if (inlineMutationBusyRef.current) return;
    setInlineMutationError(undefined);
    setEditingPromptLanguage(language);
    setPromptDraft(text);
  };
  const cancelPromptEdit = () => {
    if (inlineMutationBusyRef.current) return;
    setEditingPromptLanguage(undefined);
    setPromptDraft('');
  };
  const confirmPromptEdit = async () => {
    if (!editingPromptLanguage || inlineMutationBusyRef.current) return;
    if (await commitPrompt(editingPromptLanguage, promptDraft)) cancelPromptEdit();
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
      .filter(element => !element.matches(':disabled') && (element.getClientRects().length > 0 || element === document.activeElement));
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

  const managementActions = item && (showMutations || allowManagementActions) && (
    <details className="detail-management-actions" onKeyDown={event => {
      if (event.key !== 'Escape' || !event.currentTarget.open) return;
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.open = false;
      event.currentTarget.querySelector('summary')?.focus();
    }}>
      <summary tabIndex={0} aria-label={t('moreActions')} title={t('moreActions')}><MoreHorizontal size={20} /></summary>
      <div className="detail-management-menu">
        {showMutations && <button type="button" onClick={() => onEdit(item)}><Pencil size={16} />{t('edit')}</button>}
        {allowManagementActions && <button type="button" className="danger" disabled={deleteBusy} onClick={handleDelete}><Trash2 size={16} />{t('deleteReference')}</button>}
      </div>
    </details>
  );

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
        <header className="detail-compact-header">
          <span>{displayTitle || item?.title || t('loading')}</span>
          <button type="button" className="modal-icon-button" onClick={handleClose} aria-label={t('close')}><X size={20} /></button>
        </header>
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
                      {managementActions}
                       {showMutations && canGenerate && <button className="modal-icon-button mobile-generate-variant-button" disabled={editingPromptLanguage !== undefined || inlineMutationBusy} onClick={() => generateFromSelection(true)} aria-label={t('editThisImage')} title={t('editThisImage')}>
                         {imageEditIcon}
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
                     {showMutations && canGenerate && <button className="secondary generate-variant-button" disabled={editingPromptLanguage !== undefined || inlineMutationBusy} onClick={() => generateFromSelection(true)} aria-label={t('editThisImage')} title={t('editThisImage')}>{imageEditIcon}</button>}
                     {selectedImage && <a className="modal-icon-button download-button" href={mediaUrl(selectedImage.original_path || imageHeroPath(selectedImage))} download={downloadFileName(displayTitle || item.title, selectedImage?.original_path || imageHeroPath(selectedImage))} aria-label={t('download')} title={t('download')}><Download size={18} /></a>}
                    {allowManagementActions && <button className="modal-icon-button favorite-button" onClick={toggleFavorite} aria-label={item.favorite ? t('saved') : t('favorite')}>
                      <Heart size={18} fill={item.favorite ? 'currentColor' : 'none'} />
                    </button>}
                    {managementActions}
                  </span>
                  <button className="modal-icon-button close" onClick={handleClose} aria-label={t('close')}>
                    <X size={20} strokeWidth={2.25} />
                  </button>
                </div>
                <div className="detail-identity">
                <InlineEditableField t={t} className="collection-inline-edit" value={item.cluster?.name || ''} placeholder={t('unclustered')} inputList="detail-collection-suggestions" onCommit={value => commitInlineUpdate({ cluster_name: value.trim() || null })} editable={allowManagementActions} busy={inlineMutationBusy}>
                  <datalist id="detail-collection-suggestions">
                    {clusters.map(collection => <option key={collection.id} value={collection.name} />)}
                  </datalist>
                </InlineEditableField>
                <h2>
                  <InlineEditableField t={t} className="title-inline-edit" value={showMutations ? item.title : (displayTitle || item.title)} placeholder={t('titlePlaceholder')} onCommit={value => commitInlineUpdate({ title: value.trim() || item.title })} editable={allowManagementActions} busy={inlineMutationBusy} />
                </h2>
                <p className="muted metadata-row">
                  <InlineEditableField t={t} className="metadata-inline-edit" value={item.model || t('defaultModel')} placeholder={t('imageGeneratedFrom')} onCommit={value => commitInlineUpdate({ model: value.trim() || item.model })} editable={allowManagementActions} busy={inlineMutationBusy} />
                  <span>·</span>
                  <InlineEditableField t={t} className="metadata-inline-edit" value={`@${item.author || 'User'}`} placeholder="@User" onCommit={value => commitInlineUpdate({ author: value.replace(/^@/, '').trim() || 'User' })} editable={allowManagementActions} busy={inlineMutationBusy} />
                  {item.source_url && (
                    <a className="source-icon-link" href={item.source_url} target="_blank" rel="noreferrer" aria-label={t('source')}>
                      <ExternalLink size={16} />
                    </a>
                  )}
                </p>
                </div>
                <div className="prompt-blocks" aria-label={t('promptLanguage')}>
                  {(() => {
                    return (
                      <section className="prompt-block prompt-panel active" aria-label={t('cardPrompt')}>
                        <header className="prompt-block-header">
                          <div className="prompt-language-tabs tabs" role="tablist" aria-label={t('promptLanguage')} onKeyDown={event => {
                            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                            event.preventDefault();
                            const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
                            const current = tabs.indexOf(document.activeElement as HTMLButtonElement);
                            const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
                            tabs[next]?.click();
                            tabs[next]?.focus();
                          }}>
                            {promptDisplayOrder.map(promptLanguage => {
                              const tabPrompt = item.prompts.find(prompt => prompt.language === promptLanguage);
                              const isOriginalPrompt = Boolean(tabPrompt?.is_original || originalPrompt?.language === promptLanguage);
                              return (
                                <button
                                  type="button"
                                  role="tab"
                                  disabled={inlineMutationBusy}
                                  aria-selected={lang === promptLanguage}
                                  aria-label={`${LANG_LABELS[promptLanguage] || promptLanguage}${isOriginalPrompt ? ` · ${t('origin')}` : ''}`}
                                  tabIndex={lang === promptLanguage ? 0 : -1}
                                  className={`prompt-language-tab ${lang === promptLanguage ? 'active' : ''} ${isOriginalPrompt ? 'is-original' : ''}`}
                                  onClick={() => { setLang(promptLanguage); cancelPromptEdit(); }}
                                  title={isOriginalPrompt ? t('origin') : tabPrompt?.text.trim() ? undefined : t('promptText')}
                                  key={promptLanguage}
                                >
                                  {LANG_LABELS[promptLanguage] || promptLanguage}
                                </button>
                              );
                            })}
                          </div>
                          <span className="prompt-block-actions">
                            <button type="button" className="prompt-copy-icon" onClick={() => handleCopyPrompt(prompt?.text || '')} aria-label={t('copyPrompt')} title={t('copyPrompt')} disabled={!prompt?.text}>
                              <Copy size={18} strokeWidth={1.75} aria-hidden="true" />
                            </button>
                            {allowManagementActions && <button type="button" className="prompt-edit-icon" onClick={() => startPromptEdit(lang, prompt?.text || '')} aria-label={t('edit')} title={t('edit')}>
                              <Pencil size={18} strokeWidth={1.75} aria-hidden="true" />
                            </button>}
                            {showMutations && canGenerate && <button type="button" className="prompt-generate-action" disabled={editingPromptLanguage !== undefined || inlineMutationBusy} onClick={() => generateFromSelection(false)} aria-label={t('reusePrompt')} title={t('reusePrompt')}>{imageGenerateIcon}</button>}
                          </span>
                        </header>
                        <div className="prompt-panel-body">
                          {allowManagementActions && editingPromptLanguage === lang ? (
                            <>
                              <textarea
                                className="prompt-edit-textarea"
                                value={promptDraft}
                                disabled={inlineMutationBusy}
                                placeholder={t('promptText')}
                                autoFocus
                                onChange={event => setPromptDraft(event.target.value)}
                                onKeyDown={event => {
                                  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') confirmPromptEdit();
                                  if (event.key === 'Escape') cancelPromptEdit();
                                }}
                              />
                              <span className="prompt-edit-controls">
                                 <button type="button" className="inline-edit-confirm" onClick={confirmPromptEdit} disabled={inlineMutationBusy} aria-label={t('confirmEdit')}><Check size={14} /></button>
                                 <button type="button" className="inline-edit-cancel" onClick={cancelPromptEdit} disabled={inlineMutationBusy} aria-label={t('cancelEdit')}><X size={14} /></button>
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

                {inlineMutationError && <p className="provider-message" role="alert">{inlineMutationError}</p>}
                {(selectedImage?.generation_job_id || selectedImageGenerationSource) && (
                  <details className="generation-details">
                    <summary tabIndex={0}>{t('generationDetails')}</summary>
                    {selectedImageGenerationSource && <p className="image-generation-provenance"><span>{t('generatedWith')}</span><strong>{selectedImageGenerationSource}</strong></p>}
                    {selectedImage?.generation_job_id && canGenerate && <button type="button" className="generation-history-link" onClick={() => onGenerationHistory(item, selectedImage.generation_job_id!)}>{t('imageGenerationHistory')}<ArrowRight size={14} aria-hidden="true" /></button>}
                    {selectedImage && hasDistinctGenerationPrompt && (
                      <section className="prompt-block prompt-panel active" aria-label={t('imagePrompt')}>
                        <header className="prompt-block-header">
                          <strong>{t('imagePrompt')}</strong>
                          <span className="prompt-block-actions">
                            <button type="button" className="prompt-copy-icon" onClick={() => handleCopyPrompt(selectedImage.generation_prompt_text || '')} disabled={!selectedImage.generation_prompt_text} aria-label={t('copyImagePrompt')}><Copy size={15} /></button>
                          </span>
                        </header>
                        <div className="prompt-panel-body"><div className="prompt-inline-edit"><p>{selectedImage.generation_prompt_text}</p></div></div>
                      </section>
                    )}
                  </details>
                )}
                <InlineEditableTextArea t={t} className="notes-inline-edit" value={item.notes || ''} placeholder={t('addNote')} onCommit={value => commitInlineUpdate({ notes: value.trim() || null })} editable={allowManagementActions} busy={inlineMutationBusy} />

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
