const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal dialog focus handling: moves focus into the node on mount (to a
 * `[data-autofocus]` element if present), keeps Tab inside it, calls onEscape on
 * Escape, and returns focus to the previously focused element on destroy.
 *
 * @type {import('svelte/action').Action<HTMLElement, { onEscape?: () => void } | undefined>}
 */
export function focusTrap(node, params) {
  let onEscape = params?.onEscape;
  const opener = document.activeElement;
  /** @returns {HTMLElement[]} */
  const focusables = () => Array.from(node.querySelectorAll(FOCUSABLE));

  const initial = /** @type {HTMLElement | null} */ (node.querySelector('[data-autofocus]')) || focusables()[0];
  (initial || node).focus();

  /** @param {KeyboardEvent} event */
  function handleKeydown(event) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onEscape?.();
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusables();
    if (items.length === 0) {
      event.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === node)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  node.addEventListener('keydown', handleKeydown);
  return {
    update(next) {
      onEscape = next?.onEscape;
    },
    destroy() {
      node.removeEventListener('keydown', handleKeydown);
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    }
  };
}
