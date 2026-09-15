/**
 * Keeping the keyboard inside a dialog, and putting it back afterwards.
 *
 * `aria-modal` tells a screen reader that the rest of the page is inert. It
 * tells Tab nothing at all: without this, the third press moves focus behind an
 * open dialog, into a page the user was told they had left, and the way back is
 * to keep pressing until it wraps around. A sighted mouse user never sees it; a
 * keyboard user is the only one who meets it, which is exactly why it goes
 * unnoticed.
 *
 * Three behaviours, and no more than three. Focus moves into the dialog when it
 * opens, Tab and Shift+Tab cycle within it, and focus returns to whatever opened
 * it when it closes. Escape is offered separately, because a dialog that must
 * not be dismissed by accident — one that is asking for a deletion, say — should
 * be able to decline it.
 */

import { useEffect, type RefObject } from 'react';

/** What a keyboard can reach: the standard set, minus anything the page has
 *  deliberately removed from the order with a negative tabindex. */
const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])', 'select:not([disabled])',
  'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',');

export function focusableWithin(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(FOCUSABLE)]
    // `offsetParent` is null for anything display:none, which is how a hidden
    // control would otherwise become a stop on the way round.
    .filter(element => element.offsetParent !== null || element === document.activeElement);
}

/** Where Tab should land, given where it is now.
 *
 *  Pure, so the wrap-around — the part that is actually easy to get wrong — can
 *  be tested without a DOM. Returns null when focus is already somewhere the
 *  browser will handle correctly on its own. */
export function nextFocus(
  order: readonly HTMLElement[], current: Element | null, backwards: boolean,
): HTMLElement | null {
  if (order.length === 0) return null;
  const first = order[0];
  const last = order[order.length - 1];
  const index = order.indexOf(current as HTMLElement);
  // Focus outside the dialog entirely — a click on the page behind, or a browser
  // that moved it — comes back to the near end rather than being left there.
  if (index === -1) return backwards ? last : first;
  if (backwards && current === first) return last;
  if (!backwards && current === last) return first;
  return null;
}

export interface TrapOptions {
  /** Called on Escape. Omitted where a dialog should not be dismissed that way. */
  onEscape?: () => void;
}

/**
 * Hold the keyboard inside `container` while `open`, and restore focus after.
 *
 * The element focused at open time is remembered rather than searched for
 * afterwards: by the time the dialog closes, the button that opened it may not
 * be on the page any more, and guessing would move focus somewhere arbitrary.
 */
export function useFocusTrap(
  container: RefObject<HTMLElement | null>, open: boolean, options: TrapOptions = {},
): void {
  const { onEscape } = options;
  useEffect(() => {
    const element = container.current;
    if (!open || !element) return;
    const restoreTo = document.activeElement as HTMLElement | null;
    const order = focusableWithin(element);
    // The dialog itself when it holds nothing focusable, so focus is inside it
    // either way and the first Tab starts from the right place.
    (order[0] ?? element).focus?.();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && onEscape) {
        event.preventDefault();
        onEscape();
        return;
      }
      if (event.key !== 'Tab') return;
      const moveTo = nextFocus(focusableWithin(element), document.activeElement, event.shiftKey);
      if (!moveTo) return;
      event.preventDefault();
      moveTo.focus();
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      // Only if the page has not already moved on: a dialog that closed because
      // the user navigated should not drag focus backwards.
      if (restoreTo?.isConnected) restoreTo.focus?.();
    };
  }, [container, open, onEscape]);
}
