<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { clientsApi } from '$lib/api';
  import { clientSortOptions } from '$lib/clients/config';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import ClientListCard from '$lib/components/clients/ClientListCard.svelte';
  import ClientsToolbar from '$lib/components/clients/ClientsToolbar.svelte';

  let clients = [];
  let loading = true;
  let searchQuery = '';
  let sortBy = 'created_at';
  let sortDir = 'desc';
  let showDeleteModal = false;
  let deleteTargetId = null;
  let deleteTargetName = '';
  let deleting = false;

  $: selectedSortOption = `${sortBy}-${sortDir}`;

  onMount(async () => {
    await loadClients();
  });

  async function loadClients() {
    loading = true;
    try {
      const params = { sort_by: sortBy, sort_dir: sortDir };
      if (searchQuery) params.search = searchQuery;
      clients = await clientsApi.list(params);
    } catch (error) {
      toast.error('Failed to load clients');
    } finally {
      loading = false;
    }
  }

  function handleSortChange(value) {
    const option = clientSortOptions.find((item) => item.value === value);
    if (!option) return;
    sortBy = option.field;
    sortDir = option.dir;
    loadClients();
  }

  function openDeleteModal(client) {
    deleteTargetId = client.id;
    deleteTargetName = client.business_name || client.name;
    showDeleteModal = true;
  }

  async function confirmDelete() {
    if (!deleteTargetId) return;
    deleting = true;
    try {
      await clientsApi.delete(deleteTargetId);
      toast.success('Client moved to trash');
      showDeleteModal = false;
      await loadClients();
    } catch (error) {
      toast.error('Failed to delete client');
    } finally {
      deleting = false;
      deleteTargetId = null;
      deleteTargetName = '';
    }
  }

  function cancelDelete() {
    showDeleteModal = false;
    deleteTargetId = null;
    deleteTargetName = '';
  }
</script>

<Header title="Clients" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Clients</h1>
      <p class="page-subtitle">{clients.length} client{clients.length !== 1 ? 's' : ''}</p>
    </div>
    <a href="/clients/new" class="btn btn-primary">
      <Icon name="plus" size="sm" />
      New Client
    </a>
  </div>

  <ClientsToolbar
    bind:searchQuery
    {selectedSortOption}
    sortOptions={clientSortOptions}
    on:search={loadClients}
    on:clear={() => {
      searchQuery = '';
      loadClients();
    }}
    on:sortchange={(event) => handleSortChange(event.detail)}
  />

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if clients.length > 0}
    <div class="clients-grid">
      {#each clients as client}
        <ClientListCard
          {client}
          on:open={(event) => goto(`/clients/${event.detail}`)}
          on:edit={(event) => goto(`/clients/${event.detail}/edit`)}
          on:delete={(event) => openDeleteModal(event.detail)}
        />
      {/each}
    </div>
  {:else}
    <div class="empty-state">
      <div class="empty-state-icon">
        <Icon name="users" size="xl" />
      </div>
      <div class="empty-state-title">{searchQuery ? 'No clients found' : 'No clients yet'}</div>
      <div class="empty-state-description">
        {#if searchQuery}
          Try a different search term or create a new client.
        {:else}
          Add your first client to start creating invoices.
        {/if}
      </div>
      <button class="btn btn-primary mt-6" on:click={() => goto('/clients/new')}>
        <Icon name="plus" size="sm" />
        Add Client
      </button>
    </div>
  {/if}
</div>

<ConfirmModal
  show={showDeleteModal}
  title="Delete Client"
  message="Move &quot;{deleteTargetName}&quot; to trash? You can restore them later from the Trash."
  confirmText="Delete"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deleting}
  onConfirm={confirmDelete}
  onCancel={cancelDelete}
/>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 1400px;
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

  .clients-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: var(--space-4);
  }

  .empty-state {
    text-align: center;
    padding: var(--space-12);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
  }

  .empty-state-icon {
    color: var(--color-text-muted);
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

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
