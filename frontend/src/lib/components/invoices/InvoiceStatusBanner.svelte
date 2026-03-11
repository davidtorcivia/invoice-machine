<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { statusConfig } from '$lib/invoices/list';

  export let status = 'draft';

  const dispatch = createEventDispatcher();

  /**
   * @param {Event} event
   * @returns {HTMLSelectElement}
   */
  function getSelectTarget(event) {
    return /** @type {HTMLSelectElement} */ (event.currentTarget);
  }
</script>

<div class="status-banner">
  <div class="status-info">
    <span class="status-label">Status</span>
    <div class="status-select-wrapper">
      <select
        class="status-select {statusConfig[status]?.class || 'badge-draft'}"
        value={status}
        on:change={(event) => dispatch('statuschange', getSelectTarget(event).value)}
      >
        <option value="draft">Draft</option>
        <option value="sent">Sent</option>
        <option value="paid">Paid</option>
        <option value="overdue">Overdue</option>
        <option value="cancelled">Cancelled</option>
      </select>
    </div>
  </div>

  <div class="status-actions">
    {#if status === 'draft'}
      <button class="btn btn-secondary btn-sm" on:click={() => dispatch('statuschange', 'sent')}>
        <Icon name="send" size="sm" />
        Mark as Sent
      </button>
    {/if}
    {#if status === 'sent' || status === 'overdue'}
      <button class="btn btn-primary btn-sm" on:click={() => dispatch('statuschange', 'paid')}>
        <Icon name="check" size="sm" />
        Mark as Paid
      </button>
    {/if}
    {#if status === 'paid'}
      <button class="btn btn-secondary btn-sm" on:click={() => dispatch('statuschange', 'sent')}>
        <Icon name="refresh" size="sm" />
        Revert to Sent
      </button>
    {/if}
    {#if status === 'sent' || status === 'paid'}
      <button class="btn btn-ghost btn-sm" on:click={() => dispatch('statuschange', 'draft')}>
        <Icon name="pencil" size="sm" />
        Back to Draft
      </button>
    {/if}
    <button class="btn btn-ghost btn-sm text-danger" on:click={() => dispatch('delete')}>
      <Icon name="trash" size="sm" />
      Delete
    </button>
  </div>
</div>

<style>
  .status-banner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-5) var(--space-6);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .status-info {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .status-label {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .status-select-wrapper {
    position: relative;
  }

  .status-select {
    appearance: none;
    padding: var(--space-2) var(--space-6) var(--space-2) var(--space-4);
    font-size: 0.875rem;
    font-weight: 500;
    border-radius: var(--radius-full);
    border: none;
    cursor: pointer;
    text-transform: capitalize;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
  }

  .status-select.badge-draft {
    background-color: var(--color-bg-sunken);
    color: var(--color-text-secondary);
  }

  .status-select.badge-sent {
    background-color: var(--color-info-light);
    color: var(--color-info);
  }

  .status-select.badge-paid {
    background-color: var(--color-success-light);
    color: var(--color-success);
  }

  .status-select.badge-overdue {
    background-color: var(--color-danger-light);
    color: var(--color-danger);
  }

  .status-select.badge-cancelled {
    background-color: var(--color-bg-sunken);
    color: var(--color-text-tertiary);
  }

  .status-select:focus {
    outline: none;
    box-shadow: 0 0 0 2px var(--color-border-focus);
  }

  .status-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  @media (max-width: 768px) {
    .status-banner {
      flex-direction: column;
      align-items: stretch;
    }

    .status-actions {
      justify-content: flex-start;
    }
  }

  @media (max-width: 480px) {
    .status-banner {
      padding: var(--space-4);
    }

    .status-actions {
      flex-direction: column;
    }

    .status-actions .btn {
      width: 100%;
      justify-content: center;
    }
  }
</style>
