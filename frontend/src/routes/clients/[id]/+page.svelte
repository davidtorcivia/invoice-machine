<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { clientsApi, invoicesApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import ClientInvoicesCard from '$lib/components/clients/ClientInvoicesCard.svelte';
  import ClientSidebarDetails from '$lib/components/clients/ClientSidebarDetails.svelte';
  import ClientStatsGrid from '$lib/components/clients/ClientStatsGrid.svelte';

  $: clientId = $page.params.id || '';

  let client = null;
  let invoices = [];
  let loading = true;
  let showDeleteModal = false;
  let deleting = false;

  $: if (clientId) loadData();

  async function loadData() {
    loading = true;
    try {
      const [clientData, invoicesData] = await Promise.all([
        clientsApi.get(clientId),
        invoicesApi.list({ client_id: clientId })
      ]);
      client = clientData;
      invoices = invoicesData;
    } catch (error) {
      toast.error('Failed to load client');
      goto('/clients');
    } finally {
      loading = false;
    }
  }

  function openDeleteModal() {
    showDeleteModal = true;
  }

  async function confirmDelete() {
    deleting = true;
    try {
      await clientsApi.delete(clientId);
      toast.success('Client moved to trash');
      goto('/clients');
    } catch (error) {
      toast.error('Failed to delete client');
    } finally {
      deleting = false;
    }
  }

  function cancelDelete() {
    showDeleteModal = false;
  }
</script>

<Header title={client ? (client.business_name || client.name) : 'Client'} />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if client}
    <div class="page-header">
      <div class="page-header-text">
        <h1>{client.business_name || client.name}</h1>
        {#if client.business_name && client.name}
          <p class="page-subtitle">{client.name}</p>
        {/if}
      </div>
      <div class="page-actions">
        <a href="/clients/{clientId}/edit" class="btn btn-secondary">
          <Icon name="pencil" size="sm" />
          Edit
        </a>
        <a href="/invoices/new?client={clientId}" class="btn btn-primary">
          <Icon name="plus" size="sm" />
          New Invoice
        </a>
      </div>
    </div>

    <div class="client-layout">
      <div class="client-main">
        <ClientStatsGrid {invoices} />
        <ClientInvoicesCard {invoices} on:newinvoice={() => goto(`/invoices/new?client=${clientId}`)} on:openinvoice={(event) => goto(`/invoices/${event.detail}`)} />
      </div>

      <div class="client-sidebar">
        <ClientSidebarDetails {client} />

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Actions</h3>
          </div>
          <div class="action-list">
            <button class="btn btn-secondary btn-block" on:click={() => goto(`/clients/${clientId}/edit`)}>
              <Icon name="pencil" size="sm" />
              Edit Client
            </button>
            <button class="btn btn-ghost btn-block text-danger" on:click={openDeleteModal}>
              <Icon name="trash" size="sm" />
              Delete Client
            </button>
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>

<ConfirmModal
  show={showDeleteModal}
  title="Delete Client"
  message="Move &quot;{client?.business_name || client?.name}&quot; to trash? You can restore them later from the Trash."
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
    flex-wrap: wrap;
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

  .page-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
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

  .client-layout {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: var(--space-6);
  }

  .client-main,
  .client-sidebar {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .action-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .btn-block {
    width: 100%;
    justify-content: center;
  }

  @media (max-width: 1024px) {
    .client-layout {
      grid-template-columns: 1fr;
    }

    .client-sidebar {
      order: -1;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .page-header {
      flex-direction: column;
      align-items: stretch;
    }

    .page-actions {
      width: 100%;
    }

    .page-actions .btn {
      flex: 1;
    }
  }

  @media (max-width: 480px) {
    .page-header h1 {
      font-size: 1.25rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
    }
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
