<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { invoicesApi } from '$lib/api';
  import { formatDate, formatCurrency, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

  $: id = $page.params.id;

  let invoice = null;
  let items = [];
  let loading = true;
  let generatingPdf = false;

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
    await loadInvoice();
  });

  async function loadInvoice() {
    loading = true;
    try {
      const data = await invoicesApi.get(id);
      invoice = data;
      items = data.items || [];
    } catch (error) {
      toast.error('Failed to load invoice');
    } finally {
      loading = false;
    }
  }

  async function generatePdf() {
    generatingPdf = true;
    try {
      const result = await invoicesApi.generatePdf(id);
      toast.success('PDF generated successfully');
      window.open(result.pdf_url, '_blank');
    } catch (error) {
      toast.error('Failed to generate PDF');
    } finally {
      generatingPdf = false;
    }
  }

  async function downloadPdf() {
    window.open(invoicesApi.getPdfUrl(id), '_blank');
  }

  async function updateStatus(status) {
    try {
      await invoicesApi.update(id, { status });
      toast.success(`Invoice marked as ${status}`);
      await loadInvoice();
    } catch (error) {
      toast.error('Failed to update status');
    }
  }

  function openDeleteModal() {
    showDeleteModal = true;
  }

  async function confirmDelete() {
    deleting = true;
    try {
      await invoicesApi.delete(id);
      toast.success('Invoice moved to trash');
      goto('/invoices');
    } catch (error) {
      toast.error('Failed to delete invoice');
    } finally {
      deleting = false;
    }
  }

  function cancelDelete() {
    showDeleteModal = false;
  }
</script>

<Header title={invoice ? `Invoice #${invoice.invoice_number}` : 'Invoice'} />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if invoice}
    <div class="page-header">
      <div class="page-header-text">
        <h1>Invoice #{invoice.invoice_number}</h1>
        <p class="page-subtitle">{invoice.client_business || invoice.client_name || ''}</p>
      </div>
      <div class="page-actions">
        <a href="/invoices/{id}/edit" class="btn btn-secondary">
          <Icon name="pencil" size="sm" />
          Edit
        </a>
        <button class="btn btn-secondary" on:click={generatePdf} disabled={generatingPdf}>
          <Icon name="refresh" size="sm" />
          {generatingPdf ? 'Generating...' : 'Generate PDF'}
        </button>
        <button class="btn btn-primary" on:click={downloadPdf}>
          <Icon name="download" size="sm" />
          Download PDF
        </button>
      </div>
    </div>

    <div class="invoice-layout">
      <!-- Main Content -->
      <div class="invoice-main">
        <!-- Status Banner -->
        <div class="status-banner">
          <div class="status-info">
            <span class="status-label">Status</span>
            <div class="status-select-wrapper">
              <select
                class="status-select {statusConfig[invoice.status]?.class || 'badge-draft'}"
                value={invoice.status}
                on:change={(e) => updateStatus(e.target.value)}
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
            {#if invoice.status === 'draft'}
              <button class="btn btn-secondary btn-sm" on:click={() => updateStatus('sent')}>
                <Icon name="send" size="sm" />
                Mark as Sent
              </button>
            {/if}
            {#if invoice.status === 'sent' || invoice.status === 'overdue'}
              <button class="btn btn-primary btn-sm" on:click={() => updateStatus('paid')}>
                <Icon name="check" size="sm" />
                Mark as Paid
              </button>
            {/if}
            {#if invoice.status === 'paid'}
              <button class="btn btn-secondary btn-sm" on:click={() => updateStatus('sent')}>
                <Icon name="refresh" size="sm" />
                Revert to Sent
              </button>
            {/if}
            {#if invoice.status === 'sent' || invoice.status === 'paid'}
              <button class="btn btn-ghost btn-sm" on:click={() => updateStatus('draft')}>
                <Icon name="pencil" size="sm" />
                Back to Draft
              </button>
            {/if}
            <button class="btn btn-ghost btn-sm text-danger" on:click={openDeleteModal}>
              <Icon name="trash" size="sm" />
              Delete
            </button>
          </div>
        </div>

        <!-- Client Info -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Bill To</h3>
          </div>
          <div class="client-info">
            {#if invoice.client_business}
              <div class="client-business">{invoice.client_business}</div>
            {/if}
            {#if invoice.client_name}
              <div class="client-contact">Attn: {invoice.client_name}</div>
            {/if}
            {#if invoice.client_address}
              <div class="client-address">{invoice.client_address}</div>
            {/if}
            {#if invoice.client_email}
              <div class="client-email">
                <Icon name="mail" size="sm" />
                {invoice.client_email}
              </div>
            {/if}
          </div>
        </div>

        <!-- Line Items -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Line Items</h3>
          </div>

          {#if items.length > 0}
            <div class="items-table-wrapper">
              <table class="items-table">
                <thead>
                  <tr>
                    <th class="col-desc">Description</th>
                    <th class="col-price text-right">Price</th>
                    <th class="col-qty text-center">Qty</th>
                    <th class="col-total text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {#each items as item, i}
                    <tr>
                      <td class="col-desc">{item.description}</td>
                      <td class="col-price text-right text-secondary">{formatCurrency(item.unit_price)}</td>
                      <td class="col-qty text-center text-secondary">{item.quantity}</td>
                      <td class="col-total text-right font-medium">{formatCurrency(item.total)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>

            <div class="totals">
              <div class="total-row">
                <span class="total-label">Subtotal</span>
                <span class="total-value">{formatCurrency(invoice.subtotal)}</span>
              </div>
              <div class="total-row total-final">
                <span class="total-label">Total</span>
                <span class="total-value total-amount">{formatCurrency(invoice.total)}</span>
              </div>
            </div>
          {:else}
            <p class="text-secondary">No line items.</p>
          {/if}
        </div>

        <!-- Notes -->
        {#if invoice.notes}
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Notes</h3>
            </div>
            <p class="notes-text">{invoice.notes}</p>
          </div>
        {/if}
      </div>

      <!-- Sidebar -->
      <div class="invoice-sidebar">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Details</h3>
          </div>
          <dl class="detail-list">
            <div class="detail-item">
              <dt>Invoice Number</dt>
              <dd class="font-mono">#{invoice.invoice_number}</dd>
            </div>
            <div class="detail-item">
              <dt>Issue Date</dt>
              <dd>{formatDate(invoice.issue_date, 'long')}</dd>
            </div>
            <div class="detail-item">
              <dt>Due Date</dt>
              <dd>{invoice.due_date ? formatDate(invoice.due_date, 'long') : '---'}</dd>
            </div>
            <div class="detail-item">
              <dt>Payment Terms</dt>
              <dd>Net {invoice.payment_terms_days} days</dd>
            </div>
            <div class="detail-item">
              <dt>Currency</dt>
              <dd>{invoice.currency_code || 'USD'}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  {/if}
</div>

<ConfirmModal
  show={showDeleteModal}
  title="Delete Invoice"
  message="Move invoice #{invoice?.invoice_number} to trash? You can restore it later from the Trash."
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

  .invoice-layout {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: var(--space-6);
  }

  .invoice-main {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

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

  .badge-lg {
    padding: var(--space-2) var(--space-4);
    font-size: 0.875rem;
  }

  .status-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  /* Client Info */
  .client-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .client-business {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .client-contact {
    color: var(--color-text-secondary);
  }

  .client-address {
    white-space: pre-line;
    color: var(--color-text-secondary);
    line-height: 1.5;
  }

  .client-email {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-primary);
    margin-top: var(--space-2);
  }

  /* Items Table */
  .items-table-wrapper {
    margin: 0 calc(var(--space-6) * -1);
    overflow-x: auto;
  }

  .items-table {
    width: 100%;
    border-collapse: collapse;
  }

  .items-table th {
    text-align: left;
    padding: var(--space-3) var(--space-6);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary);
    background: var(--color-bg-sunken);
    border-top: 1px solid var(--color-border-light);
    border-bottom: 1px solid var(--color-border-light);
  }

  .items-table td {
    padding: var(--space-4) var(--space-6);
    border-bottom: 1px solid var(--color-border-light);
  }

  .items-table tr:last-child td {
    border-bottom: none;
  }

  .col-desc { width: auto; }
  .col-price { width: 120px; }
  .col-qty { width: 80px; }
  .col-total { width: 120px; }

  /* Totals */
  .totals {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-2);
    padding-top: var(--space-4);
  }

  .total-row {
    display: flex;
    gap: var(--space-8);
    min-width: 200px;
    justify-content: space-between;
  }

  .total-label {
    color: var(--color-text-secondary);
  }

  .total-value {
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }

  .total-final {
    padding-top: var(--space-3);
    border-top: 2px solid var(--color-border);
  }

  .total-amount {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--color-primary);
  }

  .notes-text {
    white-space: pre-line;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  /* Sidebar */
  .invoice-sidebar {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
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

  @media (max-width: 1024px) {
    .invoice-layout {
      grid-template-columns: 1fr;
    }

    .invoice-sidebar {
      order: -1;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .status-banner {
      flex-direction: column;
      align-items: stretch;
    }

    .status-actions {
      justify-content: flex-start;
    }
  }

  @media (max-width: 768px) {
    .page-header {
      flex-direction: column;
      align-items: stretch;
      gap: var(--space-3);
    }

    .page-actions {
      flex-wrap: wrap;
    }

    .page-actions .btn {
      flex: 1;
      min-width: fit-content;
    }
  }

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .page-header h1 {
      font-size: 1.25rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
    }

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

    .items-table th,
    .items-table td {
      padding: var(--space-3);
      font-size: 0.8125rem;
    }

    .col-price,
    .col-qty {
      display: none;
    }

    .total-row {
      min-width: auto;
    }
  }
</style>
