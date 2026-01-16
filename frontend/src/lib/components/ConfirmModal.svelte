<script>
  import Icon from './Icons.svelte';

  export let show = false;
  export let title = 'Confirm';
  export let message = 'Are you sure?';
  export let confirmText = 'Confirm';
  export let cancelText = 'Cancel';
  export let variant = 'danger'; // 'danger', 'warning', 'primary'
  export let icon = 'warning'; // icon name
  export let loading = false;

  export let onConfirm = () => {};
  export let onCancel = () => {};

  function handleConfirm() {
    onConfirm();
  }

  function handleCancel() {
    onCancel();
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      handleCancel();
    }
  }

  $: buttonClass = variant === 'danger' ? 'btn-danger' : variant === 'warning' ? 'btn-warning' : 'btn-primary';
  $: iconClass = variant === 'danger' ? 'danger' : variant === 'warning' ? 'warning' : 'primary';
</script>

{#if show}
  <div
    class="modal-overlay"
    on:click={handleCancel}
    on:keydown={handleKeydown}
    role="button"
    tabindex="-1"
  >
    <div class="modal confirm-modal" on:click|stopPropagation role="dialog" aria-modal="true">
      <div class="modal-icon {iconClass}">
        <Icon name={icon} size="lg" />
      </div>
      <h3 class="modal-title">{title}</h3>
      <p class="modal-message">{message}</p>
      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={handleCancel} disabled={loading}>
          {cancelText}
        </button>
        <button class="btn {buttonClass}" on:click={handleConfirm} disabled={loading}>
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
  .confirm-modal {
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
