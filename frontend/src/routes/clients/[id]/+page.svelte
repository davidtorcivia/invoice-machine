<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { clientsApi, invoicesApi } from '$lib/api';
  import { formatDate, formatCurrency, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

  $: id = $page.params.id;

  let client = null;
  let invoices = [];
  let loading = true;

  // Delete modal state
  let showDeleteModal = false;
  let deleting = false;

  const statusConfig = {
    draft: { class: 'badge-draft', label: 'Draft' },
    sent: { class: 'badge-sent', label: 'Sent' },
    paid: { class: 'badge-paid', label: 'Paid' },
    overdue: { class: 'badge-overdue', label: 'Overdue' },
    cancelled: { class: 'badge-cancelled', label: 'Cancelled' },
  };

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const [clientData, invoicesData] = await Promise.all([
        clientsApi.get(id),
        invoicesApi.list({ client_id: id }),
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
      await clientsApi.delete(id);
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

  function getTotalBilled() {
    return invoices.reduce((sum, inv) => sum + parseFloat(inv.total || 0), 0);
  }

  function getTotalPaid() {
    return invoices.filter(inv => inv.status === 'paid')
      .reduce((sum, inv) => sum + parseFloat(inv.total || 0), 0);
  }

  function getTotalOutstanding() {
    return invoices.filter(inv => inv.status !== 'paid' && inv.status !== 'cancelled')
      .reduce((sum, inv) => sum + parseFloat(inv.total || 0), 0);
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
        <a href="/clients/{id}/edit" class="btn btn-secondary">
          <Icon name="pencil" size="sm" />
          Edit
        </a>
        <a href="/invoices/new?client={id}" class="btn btn-primary">
          <Icon name="plus" size="sm" />
          New Invoice
        </a>
      </div>
    </div>

    <div class="client-layout">
      <!-- Main Content -->
      <div class="client-main">
        <!-- Stats -->
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-label">Total Billed</div>
            <div class="stat-value">{formatCurrency(getTotalBilled())}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Total Paid</div>
            <div class="stat-value stat-success">{formatCurrency(getTotalPaid())}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Outstanding</div>
            <div class="stat-value stat-warning">{formatCurrency(getTotalOutstanding())}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Invoices</div>
            <div class="stat-value">{invoices.length}</div>
          </div>
        </div>

        <!-- Invoices -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Invoices</h3>
            <button class="btn btn-secondary btn-sm" on:click={() => goto(`/invoices/new?client=${id}`)}>
              <Icon name="plus" size="sm" />
              New Invoice
            </button>
          </div>

          {#if invoices.length > 0}
            <div class="table-container">
              <table class="table">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Date</th>
                    <th>Due Date</th>
                    <th>Status</th>
                    <th class="text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {#each invoices as invoice}
                    <tr on:click={() => goto(`/invoices/${invoice.id}`)} class="clickable-row">
                      <td>
                        <span class="invoice-number font-mono">#{invoice.invoice_number}</span>
                      </td>
                      <td class="text-secondary">{formatDate(invoice.issue_date)}</td>
                      <td class="text-secondary">{invoice.due_date ? formatDate(invoice.due_date) : '---'}</td>
                      <td>
                        <span class="badge {statusConfig[invoice.status]?.class || 'badge-draft'}">
                          {statusConfig[invoice.status]?.label || invoice.status}
                        </span>
                      </td>
                      <td class="text-right">
                        <span class="invoice-total">{formatCurrency(invoice.total)}</span>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <div class="empty-state-small">
              <Icon name="invoice" size="lg" />
              <p>No invoices yet</p>
              <button class="btn btn-primary btn-sm" on:click={() => goto(`/invoices/new?client=${id}`)}>
                Create Invoice
              </button>
            </div>
          {/if}
        </div>
      </div>

      <!-- Sidebar -->
      <div class="client-sidebar">
        <!-- Contact Info -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Contact Information</h3>
          </div>

          <div class="contact-info">
            {#if client.email}
              <a href="mailto:{client.email}" class="contact-item">
                <Icon name="mail" size="sm" />
                <span>{client.email}</span>
              </a>
            {/if}

            {#if client.phone}
              <a href="tel:{client.phone}" class="contact-item">
                <Icon name="phone" size="sm" />
                <span>{client.phone}</span>
              </a>
            {/if}

            {#if client.address_line1 || client.city || client.state}
              <div class="contact-item">
                <Icon name="location" size="sm" />
                <div class="address">
                  {#if client.address_line1}<div>{client.address_line1}</div>{/if}
                  {#if client.address_line2}<div>{client.address_line2}</div>{/if}
                  {#if client.city || client.state || client.postal_code}
                    <div>
                      {[client.city, client.state].filter(Boolean).join(', ')}
                      {client.postal_code || ''}
                    </div>
                  {/if}
                  {#if client.country}<div>{client.country}</div>{/if}
                </div>
              </div>
            {/if}
          </div>

          {#if !client.email && !client.phone && !client.address_line1}
            <p class="text-secondary text-sm">No contact information added.</p>
          {/if}
        </div>

        <!-- Settings -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Settings</h3>
          </div>
          <dl class="detail-list">
            <div class="detail-item">
              <dt>Payment Terms</dt>
              <dd>Net {client.payment_terms_days || 30} days</dd>
            </div>
            <div class="detail-item">
              <dt>Tax Settings</dt>
              {#if client.tax_enabled !== null}
                <dd>
                  {#if client.tax_enabled}
                    <span class="tax-badge tax-enabled">{client.tax_name || 'Tax'} @ {client.tax_rate || 0}%</span>
                  {:else}
                    <span class="tax-badge tax-disabled">Tax Disabled</span>
                  {/if}
                </dd>
              {:else}
                <dd class="text-secondary">Using global default</dd>
              {/if}
            </div>
            {#if client.notes}
              <div class="detail-item">
                <dt>Notes</dt>
                <dd class="notes-text">{client.notes}</dd>
              </div>
            {/if}
          </dl>
        </div>

        <!-- Actions -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Actions</h3>
          </div>
          <div class="action-list">
            <button class="btn btn-secondary btn-block" on:click={() => goto(`/clients/${id}/edit`)}>
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

  .client-layout {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: var(--space-6);
  }

  .client-main {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  /* Stats */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-4);
  }

  .stat-card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
  }

  .stat-label {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    margin-bottom: var(--space-2);
  }

  .stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .stat-success {
    color: var(--color-success);
  }

  .stat-warning {
    color: var(--color-warning);
  }

  /* Table */
  .clickable-row {
    cursor: pointer;
  }

  .invoice-number {
    font-weight: 600;
    color: var(--color-text);
  }

  .invoice-total {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .empty-state-small {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-8);
    color: var(--color-text-secondary);
  }

  /* Sidebar */
  .client-sidebar {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .contact-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .contact-item {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    color: var(--color-text);
    text-decoration: none;
  }

  .contact-item:hover {
    color: var(--color-primary);
  }

  .contact-item :global(.icon) {
    color: var(--color-text-tertiary);
    flex-shrink: 0;
    margin-top: 2px;
  }

  .address {
    line-height: 1.5;
  }

  .detail-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .detail-item {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .detail-item dt {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .detail-item dd {
    font-weight: 500;
    color: var(--color-text);
  }

  .notes-text {
    font-weight: 400;
    white-space: pre-line;
    line-height: 1.5;
  }

  .tax-badge {
    display: inline-flex;
    align-items: center;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm);
    font-size: 0.8125rem;
    font-weight: 500;
  }

  .tax-enabled {
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-success);
  }

  .tax-disabled {
    background: color-mix(in srgb, var(--color-text-tertiary) 15%, transparent);
    color: var(--color-text-tertiary);
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

    .stats-row {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .stats-row {
      grid-template-columns: 1fr;
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

  @media (max-width: 640px) {
    .table th:nth-child(3),
    .table td:nth-child(3) {
      display: none;
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

    .stats-row {
      gap: var(--space-3);
    }

    .table th:nth-child(2),
    .table td:nth-child(2) {
      display: none;
    }
  }
</style>
