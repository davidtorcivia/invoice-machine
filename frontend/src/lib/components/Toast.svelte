<script>
  import { toast } from '$lib/stores';
  import Icon from './Icons.svelte';
</script>

{#if $toast.length > 0}
  <div class="toast-container">
    {#each $toast as t (t.id)}
      <div
        class="toast"
        class:toast-success={t.type === 'success'}
        class:toast-error={t.type === 'error'}
        class:toast-info={t.type === 'info'}
      >
        <span class="toast-icon">
          {#if t.type === 'success'}
            <Icon name="check" size="sm" />
          {:else if t.type === 'error'}
            <Icon name="x" size="sm" />
          {:else}
            <Icon name="eye" size="sm" />
          {/if}
        </span>
        <span class="toast-message">{t.message}</span>
        <button
          class="toast-close"
          on:click={() => toast.dismiss(t.id)}
          aria-label="Close"
        >
          <Icon name="x" size="sm" />
        </button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    bottom: var(--space-6);
    right: var(--space-6);
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    pointer-events: none;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    pointer-events: auto;
    min-width: 320px;
    max-width: 420px;
    animation: slideIn 0.25s ease;
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .toast-icon {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-full);
  }

  .toast-success {
    border-left: 4px solid var(--color-success);
  }

  .toast-success .toast-icon {
    color: var(--color-success);
    background: var(--color-success-light);
  }

  .toast-error {
    border-left: 4px solid var(--color-danger);
  }

  .toast-error .toast-icon {
    color: var(--color-danger);
    background: var(--color-danger-light);
  }

  .toast-info {
    border-left: 4px solid var(--color-info);
  }

  .toast-info .toast-icon {
    color: var(--color-info);
    background: var(--color-info-light);
  }

  .toast-message {
    flex: 1;
    font-size: 0.9375rem;
    line-height: 1.4;
    color: var(--color-text);
  }

  .toast-close {
    padding: var(--space-1);
    background: transparent;
    border: none;
    color: var(--color-text-tertiary);
    cursor: pointer;
    border-radius: var(--radius-sm);
    display: flex;
    transition: all var(--transition-fast);
  }

  .toast-close:hover {
    background: var(--color-bg-hover);
    color: var(--color-text);
  }

  @media (max-width: 640px) {
    .toast-container {
      left: var(--space-4);
      right: var(--space-4);
      bottom: var(--space-4);
    }

    .toast {
      min-width: 0;
    }
  }
</style>
