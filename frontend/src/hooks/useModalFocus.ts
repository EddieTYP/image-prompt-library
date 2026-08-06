import { useEffect, useRef, type KeyboardEvent } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function isAvailableFocusTarget(element: HTMLElement | null | undefined) {
  if (
    !element?.isConnected
    || element === document.body
    || element === document.documentElement
    || element.hasAttribute('disabled')
    || element.getAttribute('aria-disabled') === 'true'
    || element.closest('[inert], [aria-hidden="true"]')
  ) return false;
  const style = window.getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0;
}

export function focusFirstAvailable(candidates: Array<HTMLElement | null | undefined>) {
  candidates.find(isAvailableFocusTarget)?.focus({ preventScroll: true });
}

function hasActiveModalOutside(
  container: HTMLElement | null,
  restoreCandidates: Array<HTMLElement | null | undefined>,
) {
  return Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]'))
    .some(dialog => (
      dialog !== container
      && dialog.getAttribute('aria-hidden') !== 'true'
      && !container?.contains(dialog)
      && !restoreCandidates.some(candidate => candidate && (dialog === candidate || dialog.contains(candidate)))
    ));
}

export function restoreFocusAfterMotion(element: HTMLElement | null, candidates: Array<HTMLElement | null | undefined>) {
  const restore = () => focusFirstAvailable(candidates);
  if (!element || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const frame = window.requestAnimationFrame(restore);
    return () => window.cancelAnimationFrame(frame);
  }
  let finished = false;
  let fallbackTimer: number | undefined;
  const finish = () => {
    if (finished) return;
    finished = true;
    element.removeEventListener('transitionend', onEnd);
    element.removeEventListener('animationend', onEnd);
    if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer);
    restore();
  };
  const onEnd = (event: Event) => {
    if (event.target === element) finish();
  };
  element.addEventListener('transitionend', onEnd);
  element.addEventListener('animationend', onEnd);
  fallbackTimer = window.setTimeout(finish, 260);
  return () => {
    if (finished) return;
    finished = true;
    element.removeEventListener('transitionend', onEnd);
    element.removeEventListener('animationend', onEnd);
    if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer);
  };
}

export function useModalFocus<T extends HTMLElement>(
  onEscape: () => void,
  options: { active?: boolean; fallbackFocusSelector?: string; secondaryFallbackFocusSelector?: string } = {},
) {
  const active = options.active ?? true;
  const containerRef = useRef<T | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    if (!active) return undefined;
    const owner = containerRef.current;
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      const container = containerRef.current;
      const initial = container?.querySelector<HTMLElement>('[data-modal-initial-focus]');
      const first = container?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      (initial || first || container)?.focus({ preventScroll: true });
    });

    return () => {
      window.cancelAnimationFrame(frame);
      const opener = openerRef.current;
      window.setTimeout(() => {
        const fallbacks = options.fallbackFocusSelector
          ? Array.from(document.querySelectorAll<HTMLElement>(options.fallbackFocusSelector))
          : [];
        const secondaryFallbacks = options.secondaryFallbackFocusSelector
          ? Array.from(document.querySelectorAll<HTMLElement>(options.secondaryFallbackFocusSelector))
          : [];
        const appFallback = document.querySelector<HTMLElement>('.toolbar-search input');
        const restoreCandidates = [opener, ...fallbacks, ...secondaryFallbacks, appFallback];
        // A new unrelated modal owns focus. A parent modal containing one of
        // our restore targets is the nested-dialog case and may safely resume.
        if (hasActiveModalOutside(owner, restoreCandidates)) return;
        focusFirstAvailable(restoreCandidates);
      }, 0);
    };
  }, [active, options.fallbackFocusSelector, options.secondaryFallbackFocusSelector]);

  const handleModalKeyDown = (event: KeyboardEvent<T>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onEscapeRef.current();
      return;
    }

    if (event.key !== 'Tab') return;
    event.stopPropagation();
    const container = containerRef.current;
    if (!container) return;
    const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter(element => !element.hasAttribute('disabled') && (element.getClientRects().length > 0 || element === document.activeElement));
    if (focusable.length === 0) {
      event.preventDefault();
      container.focus({ preventScroll: true });
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement as HTMLElement | null;
    if (!active || !container.contains(active)) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    } else if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus({ preventScroll: true });
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    }
  };

  return { containerRef, handleModalKeyDown };
}
