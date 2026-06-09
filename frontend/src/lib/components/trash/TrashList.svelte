<script>
  import { createEventDispatcher } from 'svelte';
  import { formatDate } from '$lib/stores';
  import Icon from '$lib/components/Icons.svelte';
  import { getTrashItemIcon, getTrashItemName } from '$lib/trash/helpers';

  export let items = [];

  const dispatch = createEventDispatcher();
</script>

{#if items.length > 0}
  <div class="trash-list">
    {#each items as item}
      <div class="trash-item">
        <div class="trash-item-icon">
          <Icon name={getTrashItemIcon(item.type)} size="lg" />
        </div>

        <div class="trash-item-info">
          <div class="trash-item-name">{getTrashItemName(item)}</div>
          <div class="trash-item-meta">
            <span class="trash-item-type badge badge-draft">{item.type}</span>
            <span class="trash-item-date">Deleted {formatDate(item.deleted_at)}</span>
            <span class="trash-item-countdown" class:urgent={item.days_until_purge <= 7}>
              {item.days_until_purge} days until deletion
            </span>
          </div>
        </div>

        <div class="trash-item-actions">
          <button class="btn btn-secondary btn-sm" on:click={() => dispatch('restore', item)}>
            <Icon name="refresh" size="sm" />
            Restore
          </button>
        </div>
      </div>
    {/each}
  </div>
{:else}
  <div class="empty-state">
    <div class="empty-state-icon">
      <Icon name="trash" size="xl" />
    </div>
    <div class="empty-state-title">Trash is empty</div>
    <div class="empty-state-description">
      Items you delete will appear here for 90 days before being permanently removed.
    </div>
  </div>
{/if}

<style>
  .trash-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .trash-item {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-4) var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    transition: border-color var(--transition-fast);
  }

  .trash-item:hover {
    border-color: var(--color-border-focus);
  }

  .trash-item-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    color: var(--color-text-tertiary);
    flex-shrink: 0;
  }

  .trash-item-info {
    flex: 1;
    min-width: 0;
  }

  .trash-item-name {
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: var(--space-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .trash-item-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .trash-item-type {
    text-transform: capitalize;
  }

  .trash-item-countdown {
    color: var(--color-text-tertiary);
  }

  .trash-item-countdown.urgent {
    color: var(--color-warning);
    font-weight: 500;
  }

  .trash-item-actions {
    flex-shrink: 0;
  }

  .empty-state {
    text-align: center;
    padding: var(--space-12);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
  }

  .empty-state-icon {
    color: var(--color-text-tertiary);
    margin-bottom: var(--space-4);
  }

  .empty-state-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: var(--space-2);
  }

  .empty-state-description {
    color: var(--color-text-secondary);
  }

  @media (max-width: 768px) {
    .trash-item {
      flex-direction: column;
      align-items: stretch;
    }

    .trash-item-actions .btn {
      width: 100%;
      justify-content: center;
    }
  }
</style>
