<script>
  import { createEventDispatcher } from 'svelte';
  import { fly } from 'svelte/transition';
  import Icon from '$lib/components/Icons.svelte';

  export let selectedCount = 0;
  export let canMarkSent = false;
  export let canMarkPaid = false;

  const dispatch = createEventDispatcher();
</script>

{#if selectedCount > 0}
  <div class="bulk-action-bar" transition:fly={{ y: 50, duration: 200 }}>
    <div class="bulk-action-info">
      <span class="selection-count">{selectedCount} selected</span>
      <button class="btn btn-ghost btn-sm" on:click={() => dispatch('clear')}>
        Clear
      </button>
    </div>
    <div class="bulk-action-buttons">
      {#if canMarkSent}
        <button class="btn btn-secondary btn-sm" on:click={() => dispatch('action', 'mark_sent')} title="Mark selected draft invoices as sent">
          <Icon name="send" size="sm" />
          <span class="btn-label">Mark Sent</span>
        </button>
      {/if}
      {#if canMarkPaid}
        <button class="btn btn-secondary btn-sm" on:click={() => dispatch('action', 'mark_paid')} title="Mark selected sent or overdue invoices as paid">
          <Icon name="check" size="sm" />
          <span class="btn-label">Mark Paid</span>
        </button>
      {/if}
      <button class="btn btn-danger btn-sm" on:click={() => dispatch('action', 'delete')} title="Delete selected invoices">
        <Icon name="trash" size="sm" />
        <span class="btn-label">Delete</span>
      </button>
    </div>
  </div>
{/if}

<style>
  .bulk-action-bar {
    position: fixed;
    left: 50%;
    bottom: var(--space-6);
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    width: min(720px, calc(100% - 2rem));
    padding: var(--space-4);
    background: color-mix(in srgb, var(--color-bg-elevated) 92%, white);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-lg);
    z-index: 30;
    backdrop-filter: blur(12px);
  }

  .bulk-action-info,
  .bulk-action-buttons {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .selection-count {
    font-weight: 600;
    color: var(--color-text);
  }

  @media (max-width: 768px) {
    .bulk-action-bar {
      flex-direction: column;
      align-items: stretch;
    }

    .bulk-action-buttons {
      justify-content: stretch;
    }

    .bulk-action-buttons :global(.btn) {
      flex: 1;
      justify-content: center;
    }
  }
</style>
