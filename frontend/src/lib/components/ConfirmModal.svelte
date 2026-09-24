<script>
  import Icon from './Icons.svelte';
  import { focusTrap } from '$lib/focusTrap';

  /**
   * @typedef {Object} Props
   * @property {boolean} [show]
   * @property {string} [title]
   * @property {string} [message]
   * @property {string} [confirmText]
   * @property {string} [cancelText] empty hides the cancel button
   * @property {'danger' | 'warning' | 'primary'} [variant]
   * @property {'danger' | 'warning' | 'primary' | undefined} [confirmVariant]
   * @property {string} [icon]
   * @property {boolean} [loading]
   * @property {() => void} [onConfirm]
   * @property {() => void} [onCancel]
   */

  /** @type {Props} */
  let {
    show = false,
    title = 'Confirm',
    message = 'Are you sure?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    variant = 'danger',
    confirmVariant = undefined,
    icon = 'warning',
    loading = false,
    onConfirm = () => {},
    onCancel = () => {}
  } = $props();

  function handleConfirm() {
    onConfirm();
  }

  function handleCancel() {
    onCancel();
  }

  let activeVariant = $derived(confirmVariant || variant);
  let buttonClass = $derived(activeVariant === 'danger' ? 'btn-danger' : activeVariant === 'warning' ? 'btn-warning' : 'btn-primary');
  let iconClass = $derived(activeVariant === 'danger' ? 'danger' : activeVariant === 'warning' ? 'warning' : 'primary');
</script>

{#if show}
  <div class="modal-overlay" role="presentation">
    <button type="button" class="modal-backdrop" aria-label="Close confirmation dialog" onclick={handleCancel}></button>
    <div
      use:focusTrap={{ onEscape: handleCancel }}
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
        {#if cancelText}
          <button class="btn btn-secondary" onclick={handleCancel} disabled={loading}>
            {cancelText}
          </button>
        {/if}
        <button class="btn {buttonClass}" data-autofocus onclick={handleConfirm} disabled={loading}>
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
