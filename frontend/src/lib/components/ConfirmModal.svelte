<script>
  import { tick } from 'svelte';
  import Icon from './Icons.svelte';

  /** @type {boolean} */
  export let show = false;
  /** @type {string} */
  export let title = 'Confirm';
  /** @type {string} */
  export let message = 'Are you sure?';
  /** @type {string} */
  export let confirmText = 'Confirm';
  /** @type {string} */
  export let cancelText = 'Cancel';
  /** @type {'danger' | 'warning' | 'primary'} */
  export let variant = 'danger'; // 'danger', 'warning', 'primary'
  /** @type {'danger' | 'warning' | 'primary' | undefined} */
  export let confirmVariant = undefined;
  /** @type {string} */
  export let icon = 'warning'; // icon name
  /** @type {boolean} */
  export let loading = false;

  /** @type {() => void} */
  export let onConfirm = () => {};
  /** @type {() => void} */
  export let onCancel = () => {};

  /** @type {HTMLElement | null} */
  let dialogEl = null;
  /** @type {HTMLButtonElement | null} */
  let confirmBtn = null;
  /** @type {Element | null} */
  let previouslyFocused = null;
  let wasShown = false;

  // Focus the primary action on open; restore focus to the trigger on close.
  $: if (show && !wasShown) {
    wasShown = true;
    openModal();
  } else if (!show && wasShown) {
    wasShown = false;
    restoreFocus();
  }

  async function openModal() {
    if (typeof document !== 'undefined') {
      previouslyFocused = document.activeElement;
    }
    await tick();
    confirmBtn?.focus();
  }

  function restoreFocus() {
    if (previouslyFocused && previouslyFocused instanceof HTMLElement) {
      previouslyFocused.focus();
    }
    previouslyFocused = null;
  }

  function handleConfirm() {
    onConfirm();
  }

  function handleCancel() {
    onCancel();
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      handleCancel();
      return;
    }
    // Simple focus trap so Tab stays within the dialog.
    if (e.key === 'Tab' && dialogEl) {
      /** @type {NodeListOf<HTMLElement>} */
      const focusables = dialogEl.querySelectorAll('button:not([disabled])');
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  $: activeVariant = confirmVariant || variant;
  $: buttonClass = activeVariant === 'danger' ? 'btn-danger' : activeVariant === 'warning' ? 'btn-warning' : 'btn-primary';
  $: iconClass = activeVariant === 'danger' ? 'danger' : activeVariant === 'warning' ? 'warning' : 'primary';
</script>

{#if show}
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={handleKeydown}>
    <button type="button" class="modal-backdrop" aria-label="Close confirmation dialog" on:click={handleCancel}></button>
    <div
      bind:this={dialogEl}
      class="modal confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      aria-describedby="confirm-modal-message"
      tabindex="-1"
    >
      <div class="modal-icon {iconClass}">
        <Icon name={icon} size="lg" />
      </div>
      <h3 class="modal-title" id="confirm-modal-title">{title}</h3>
      <p class="modal-message" id="confirm-modal-message">{message}</p>
      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={handleCancel} disabled={loading}>
          {cancelText}
        </button>
        <button class="btn {buttonClass}" bind:this={confirmBtn} on:click={handleConfirm} disabled={loading}>
          {#if loading}
            <span class="spinner-sm"></span>
          {/if}
          {confirmText}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }

  .confirm-modal {
    position: relative;
    max-width: 400px;
    padding: var(--space-8);
    text-align: center;
  }

  .modal-icon {
    width: 64px;
    height: 64px;
    margin: 0 auto var(--space-5);
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-full);
  }

  .modal-icon.danger {
    background: var(--color-danger-light);
    color: var(--color-danger);
  }

  .modal-icon.warning {
    background: var(--color-warning-light);
    color: var(--color-warning);
  }

  .modal-icon.primary {
    background: var(--color-primary-light);
    color: var(--color-primary);
  }

  .modal-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: var(--space-3);
  }

  .modal-message {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    line-height: 1.6;
    margin-bottom: var(--space-6);
  }

  .modal-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: center;
  }

  .modal-actions .btn {
    min-width: 100px;
  }

  .btn-warning {
    background: var(--color-warning);
    color: var(--color-text-inverse);
    border-color: var(--color-warning);
  }

  .btn-warning:hover:not(:disabled) {
    background: #d97706;
    border-color: #d97706;
  }

  .spinner-sm {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    display: inline-block;
    margin-right: var(--space-2);
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 480px) {
    .confirm-modal {
      margin: var(--space-4);
      padding: var(--space-6);
    }

    .modal-actions {
      flex-direction: column;
    }

    .modal-actions .btn {
      width: 100%;
    }
  }
</style>
