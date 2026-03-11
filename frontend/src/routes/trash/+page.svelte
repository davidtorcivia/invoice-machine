<script>
  import { onMount } from 'svelte';
  import { trashApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import TrashList from '$lib/components/trash/TrashList.svelte';
  import { getTrashItemName } from '$lib/trash/helpers';

  let items = [];
  let loading = true;
  let emptying = false;
  let restoring = false;
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

    <TrashList {items} on:restore={(event) => openRestoreModal(event.detail)} />
  {/if}
</div>

<ConfirmModal
  show={showRestoreModal && !!selectedItem}
  title="Restore Item"
  message={selectedItem ? `Are you sure you want to restore ${getTrashItemName(selectedItem)}? This ${selectedItem.type} will be moved back to your active items.` : 'Restore this item?'}
  confirmText={restoring ? 'Restoring...' : 'Restore'}
  cancelText="Cancel"
  variant="primary"
  icon="refresh"
  loading={restoring}
  onConfirm={confirmRestore}
  onCancel={closeRestoreModal}
/>

<ConfirmModal
  show={showEmptyModal}
  title="Empty Trash"
  message="Are you sure you want to permanently delete all items older than 90 days? This action cannot be undone."
  confirmText={emptying ? 'Emptying...' : 'Empty Trash'}
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={emptying}
  onConfirm={confirmEmptyTrash}
  onCancel={closeEmptyModal}
/>

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

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
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

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
