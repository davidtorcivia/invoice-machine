<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { invoicesApi, clientsApi } from '$lib/api';
  import { formatDate, formatCurrency, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let invoices = [];
  let clients = [];
  let loading = true;
  let filterStatus = '';
  let filterClient = '';

  const statusConfig = {
    draft: { class: 'badge-draft', label: 'Draft' },
    sent: { class: 'badge-sent', label: 'Sent' },
    paid: { class: 'badge-paid', label: 'Paid' },
    overdue: { class: 'badge-overdue', label: 'Overdue' },
    cancelled: { class: 'badge-cancelled', label: 'Cancelled' },
  };

  function isOverdue(invoice) {
    if (invoice.status === 'paid' || invoice.status === 'cancelled' || invoice.status === 'draft') {
      return false;
    }
    if (!invoice.due_date) return false;
    const dueDate = new Date(invoice.due_date);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return dueDate < today;
  }

  function getEffectiveStatus(invoice) {
    if (isOverdue(invoice) && invoice.status !== 'overdue') {
      return 'overdue';
    }
    return invoice.status;
  }

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const params = {};
      if (filterStatus) params.status = filterStatus;
      if (filterClient) params.client_id = filterClient;

      [invoices, clients] = await Promise.all([
        invoicesApi.list(params),
        clientsApi.list(),
      ]);
    } catch (error) {
      toast.error('Failed to load invoices');
    } finally {
      loading = false;
    }
  }

  async function deleteInvoice(e, id) {
    e.stopPropagation();
    if (!confirm('Move this invoice to trash?')) return;

    try {
      await invoicesApi.delete(id);
      toast.success('Invoice moved to trash');
      await loadData();
    } catch (error) {
      toast.error('Failed to delete invoice');
    }
  }

  async function markAsPaid(e, id) {
    e.stopPropagation();
    try {
      await invoicesApi.update(id, { status: 'paid' });
      toast.success('Invoice marked as paid');
      await loadData();
    } catch (error) {
      toast.error('Failed to update invoice');
    }
  }
</script>

<Header title="Invoices" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Invoices</h1>
      <p class="page-subtitle">{invoices.length} invoice{invoices.length !== 1 ? 's' : ''}</p>
    </div>
    <a href="/invoices/new" class="btn btn-primary">
      <Icon name="plus" size="sm" />
      New Invoice
    </a>
  </div>

  <!-- Filters -->
  <div class="filters-bar">
    <div class="filter-group">
      <label for="status-filter" class="filter-label">Status</label>
      <select
        id="status-filter"
        class="select"
        bind:value={filterStatus}
        on:change={loadData}
      >
        <option value="">All Statuses</option>
        <option value="draft">Draft</option>
        <option value="sent">Sent</option>
        <option value="paid">Paid</option>
        <option value="overdue">Overdue</option>
        <option value="cancelled">Cancelled</option>
      </select>
    </div>

    <div class="filter-group">
      <label for="client-filter" class="filter-label">Client</label>
      <select
        id="client-filter"
        class="select"
        bind:value={filterClient}
        on:change={loadData}
      >
        <option value="">All Clients</option>
        {#each clients as client}
          <option value={client.id}>{client.business_name || client.name}</option>
        {/each}
      </select>
    </div>

    {#if filterStatus || filterClient}
      <button
        class="btn btn-ghost btn-sm clear-filters"
        on:click={() => { filterStatus = ''; filterClient = ''; loadData(); }}
      >
        <Icon name="x" size="sm" />
        Clear filters
      </button>
    {/if}
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if invoices.length > 0}
    <div class="table-container">
      <table class="table">
        <thead>
          <tr>
            <th>Invoice</th>
            <th>Client</th>
            <th>Date</th>
            <th>Due Date</th>
            <th>Status</th>
            <th class="text-right">Total</th>
            <th class="actions-col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each invoices as invoice}
            {@const effectiveStatus = getEffectiveStatus(invoice)}
            {@const overdue = isOverdue(invoice)}
            <tr on:click={() => goto(`/invoices/${invoice.id}`)} class="clickable-row" class:row-overdue={overdue}>
              <td>
                <span class="invoice-number font-mono">#{invoice.invoice_number}</span>
              </td>
              <td>
                <span class="client-name">{invoice.client_business || invoice.client_name || '---'}</span>
              </td>
              <td class="text-secondary">{formatDate(invoice.issue_date)}</td>
              <td class:text-overdue={overdue} class:text-secondary={!overdue}>
                {invoice.due_date ? formatDate(invoice.due_date) : '---'}
                {#if overdue}
                  <span class="overdue-indicator">overdue</span>
                {/if}
              </td>
              <td>
                <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
                  {statusConfig[effectiveStatus]?.label || effectiveStatus}
                </span>
              </td>
              <td class="text-right">
                <span class="invoice-total">{formatCurrency(invoice.total)}</span>
              </td>
              <td class="actions-col">
                <div class="action-buttons">
                  {#if invoice.status === 'sent' || invoice.status === 'overdue'}
                    <button
                      class="btn btn-ghost btn-icon btn-sm"
                      on:click={(e) => markAsPaid(e, invoice.id)}
                      title="Mark as paid"
                    >
                      <Icon name="check" size="sm" />
                    </button>
                  {/if}
                  <button
                    class="btn btn-ghost btn-icon btn-sm"
                    on:click={(e) => deleteInvoice(e, invoice.id)}
                    title="Delete"
                  >
                    <Icon name="trash" size="sm" />
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="empty-state">
      <div class="empty-state-icon">
        <Icon name="invoice" size="xl" />
      </div>
      <div class="empty-state-title">No invoices found</div>
      <div class="empty-state-description">
        {#if filterStatus || filterClient}
          Try adjusting your filters or create a new invoice.
        {:else}
          Create your first invoice to get started.
        {/if}
      </div>
      <button class="btn btn-primary mt-6" on:click={() => goto('/invoices/new')}>
        <Icon name="plus" size="sm" />
        Create Invoice
      </button>
    </div>
  {/if}
</div>

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

  .filters-bar {
    display: flex;
    align-items: flex-end;
    gap: var(--space-4);
    margin-bottom: var(--space-6);
    padding: var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .filter-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 180px;
  }

  .filter-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .clear-filters {
    margin-left: auto;
    color: var(--color-text-secondary);
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .clickable-row {
    cursor: pointer;
  }

  .row-overdue {
    background-color: rgba(239, 68, 68, 0.08);
  }

  .row-overdue:hover {
    background-color: rgba(239, 68, 68, 0.12);
  }

  .text-overdue {
    color: var(--color-danger, #dc2626);
    font-weight: 500;
  }

  .overdue-indicator {
    display: inline-block;
    margin-left: var(--space-2);
    padding: 0.125rem 0.375rem;
    font-size: 0.625rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.025em;
    color: #dc2626;
    background-color: rgba(239, 68, 68, 0.15);
    border-radius: var(--radius-sm);
  }

  .invoice-number {
    font-weight: 600;
    color: var(--color-text);
  }

  .client-name {
    font-weight: 500;
  }

  .invoice-total {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .actions-col {
    width: 100px;
    text-align: right;
  }

  .action-buttons {
    display: flex;
    gap: var(--space-1);
    justify-content: flex-end;
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .filters-bar {
      flex-direction: column;
      align-items: stretch;
    }

    .filter-group {
      min-width: 100%;
    }

    .clear-filters {
      margin-left: 0;
    }
  }

  @media (max-width: 640px) {
    .table th:nth-child(4),
    .table td:nth-child(4) {
      display: none;
    }
  }

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .filters-bar {
      padding: var(--space-4);
      gap: var(--space-3);
    }

    .table th:nth-child(3),
    .table td:nth-child(3),
    .table th:nth-child(4),
    .table td:nth-child(4) {
      display: none;
    }

    .invoice-number {
      font-size: 0.875rem;
    }

    .client-name {
      font-size: 0.8125rem;
      max-width: 100px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      display: block;
    }

    .invoice-total {
      font-size: 0.875rem;
    }

    .actions-col {
      width: 60px;
    }

    .action-buttons {
      gap: 0;
    }
  }
</style>
