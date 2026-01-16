<script>
  import { onMount } from 'svelte';
  import { trashApi } from '$lib/api';
  import { formatDate, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let items = [];
  let loading = true;
  let emptying = false;
  let restoring = false;

  // Modal states
  let showRestoreModal = false;
  let showEmptyModal = false;
  let selectedItem = null;

  onMount(async () => {
    await loadTrash();
  });

  async function loadTrash() {
    loading = true;
    try {
      items = await trashApi.list();
    } catch (error) {
      toast.error('Failed to load trash');
    } finally {
      loading = false;
    }
  }

  function openRestoreModal(item) {
    selectedItem = item;
    showRestoreModal = true;
  }

  function closeRestoreModal() {
    showRestoreModal = false;
    selectedItem = null;
  }

  async function confirmRestore() {
    if (!selectedItem) return;

    restoring = true;
    try {
      await trashApi.restore(selectedItem.type, selectedItem.id);
      toast.success('Item restored successfully');
      closeRestoreModal();
      await loadTrash();
    } catch (error) {
      toast.error('Failed to restore item');
    } finally {
      restoring = false;
    }
  }

  function openEmptyModal() {
    showEmptyModal = true;
  }

  function closeEmptyModal() {
    showEmptyModal = false;
  }

  async function confirmEmptyTrash() {
    emptying = true;
    try {
      await trashApi.empty();
      toast.success('Trash emptied successfully');
      closeEmptyModal();
      await loadTrash();
    } catch (error) {
      toast.error('Failed to empty trash');
    } finally {
      emptying = false;
    }
  }

  function getItemIcon(type) {
    return type === 'client' ? 'users' : 'invoice';
  }

  function getItemName(item) {
    if (item.type === 'client') {
      return item.name;
    }
    return `Invoice #${item.name}`;
  }
</script>

<Header title="Trash" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Trash</h1>
      <p class="page-subtitle">{items.length} item{items.length !== 1 ? 's' : ''}</p>
    </div>
    {#if items.length > 0}
      <button class="btn btn-danger" on:click={openEmptyModal}>
        <Icon name="trash" size="sm" />
        Empty Trash
      </button>
    {/if}
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <div class="trash-info">
      <Icon name="info" size="sm" />
      <p>Items in trash will be permanently deleted after 90 days.</p>
    </div>

    {#if items.length > 0}
      <div class="trash-list">
        {#each items as item}
          <div class="trash-item">
            <div class="trash-item-icon">
              <Icon name={getItemIcon(item.type)} size="lg" />
            </div>

            <div class="trash-item-info">
              <div class="trash-item-name">{getItemName(item)}</div>
              <div class="trash-item-meta">
                <span class="trash-item-type badge badge-secondary">{item.type}</span>
                <span class="trash-item-date">Deleted {formatDate(item.deleted_at)}</span>
                <span class="trash-item-countdown" class:urgent={item.days_until_purge <= 7}>
                  {item.days_until_purge} days until deletion
                </span>
              </div>
            </div>

            <div class="trash-item-actions">
              <button
                class="btn btn-secondary btn-sm"
                on:click={() => openRestoreModal(item)}
              >
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
  {/if}
</div>

<!-- Restore Confirmation Modal -->
{#if showRestoreModal && selectedItem}
  <div class="modal-overlay" on:click={closeRestoreModal} on:keydown={(e) => e.key === 'Escape' && closeRestoreModal()} role="button" tabindex="-1">
    <div class="modal confirm-modal" on:click|stopPropagation role="dialog" aria-modal="true">
      <div class="modal-icon restore">
        <Icon name="refresh" size="lg" />
      </div>
      <h3 class="modal-title">Restore Item</h3>
      <p class="modal-message">
        Are you sure you want to restore <strong>{getItemName(selectedItem)}</strong>?
      </p>
      <p class="modal-hint">
        This {selectedItem.type} will be moved back to your active items.
      </p>
      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={closeRestoreModal} disabled={restoring}>
          Cancel
        </button>
        <button class="btn btn-primary" on:click={confirmRestore} disabled={restoring}>
          {#if restoring}
            <span class="spinner-sm"></span>
            Restoring...
          {:else}
            <Icon name="check" size="sm" />
            Restore
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Empty Trash Confirmation Modal -->
{#if showEmptyModal}
  <div class="modal-overlay" on:click={closeEmptyModal} on:keydown={(e) => e.key === 'Escape' && closeEmptyModal()} role="button" tabindex="-1">
    <div class="modal confirm-modal danger" on:click|stopPropagation role="dialog" aria-modal="true">
      <div class="modal-icon danger">
        <Icon name="trash" size="lg" />
      </div>
      <h3 class="modal-title">Empty Trash</h3>
      <p class="modal-message">
        Are you sure you want to permanently delete all items older than 90 days?
      </p>
      <p class="modal-hint danger">
        This action cannot be undone. Any items that have been in trash for more than 90 days will be permanently removed.
      </p>
      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={closeEmptyModal} disabled={emptying}>
          Cancel
        </button>
        <button class="btn btn-danger" on:click={confirmEmptyTrash} disabled={emptying}>
          {#if emptying}
            <span class="spinner-sm"></span>
            Emptying...
          {:else}
            <Icon name="trash" size="sm" />
            Empty Trash
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 900px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-6);
    gap: var(--space-4);
  }

  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .page-subtitle {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    margin: var(--space-1) 0 0 0;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .trash-info {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-6);
    color: var(--color-text-secondary);
  }

  .trash-info :global(.icon) {
    color: var(--color-text-tertiary);
    flex-shrink: 0;
  }

  .trash-info p {
    font-size: 0.875rem;
    line-height: 1.5;
  }

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

  .badge-secondary {
    background: var(--color-bg-sunken);
    color: var(--color-text-secondary);
    font-weight: 500;
  }

  /* Confirmation Modal Styles */
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
    background: var(--color-primary-light);
    color: var(--color-primary);
  }

  .modal-icon.restore {
    background: var(--color-primary-light);
    color: var(--color-primary);
  }

  .modal-icon.danger {
    background: var(--color-danger-light);
    color: var(--color-danger);
  }

  .confirm-modal .modal-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: var(--space-3);
  }

  .modal-message {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    line-height: 1.5;
    margin-bottom: var(--space-2);
  }

  .modal-message strong {
    color: var(--color-text);
    font-weight: 600;
  }

  .modal-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    line-height: 1.5;
    margin-bottom: var(--space-6);
  }

  .modal-hint.danger {
    color: var(--color-danger);
    background: var(--color-danger-light);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
  }

  .modal-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: center;
  }

  .modal-actions .btn {
    min-width: 120px;
  }

  .spinner-sm {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    display: inline-block;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .trash-item {
      flex-wrap: wrap;
    }

    .trash-item-info {
      min-width: calc(100% - 64px);
    }

    .trash-item-actions {
      width: 100%;
      margin-top: var(--space-2);
    }

    .trash-item-actions .btn {
      width: 100%;
      justify-content: center;
    }

    .trash-item-meta {
      flex-direction: column;
      gap: var(--space-1);
    }

    .confirm-modal {
      margin: var(--space-4);
    }

    .modal-actions {
      flex-direction: column;
    }

    .modal-actions .btn {
      width: 100%;
    }
  }
</style>
