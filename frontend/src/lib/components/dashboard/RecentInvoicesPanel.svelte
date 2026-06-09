<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { formatCurrency, formatDate } from '$lib/stores';
  import { statusConfig, getEffectiveStatus } from '$lib/invoices/list';

  export let recentInvoices = [];

  const dispatch = createEventDispatcher();
</script>

<div class="section">
  <div class="section-header">
    <h2 class="section-title">Recent Invoices</h2>
    <a href="/invoices" class="section-link">
      View all
      <Icon name="arrowRight" size="sm" />
    </a>
  </div>

  {#if recentInvoices.length > 0}
    <div class="table-container table-view">
      <table class="table">
        <thead>
          <tr>
            <th>Invoice</th>
            <th>Client</th>
            <th>Date</th>
            <th>Status</th>
            <th class="text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {#each recentInvoices as invoice}
            {@const effectiveStatus = getEffectiveStatus(invoice)}
            <tr on:click={() => dispatch('open', invoice.id)} class="clickable-row">
              <td><span class="font-mono font-medium">#{invoice.invoice_number}</span></td>
              <td class="text-secondary">{invoice.client_business || invoice.client_name || '---'}</td>
              <td class="text-secondary">{formatDate(invoice.issue_date)}</td>
              <td>
                <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
                  {statusConfig[effectiveStatus]?.label || effectiveStatus}
                </span>
              </td>
              <td class="text-right font-medium">{formatCurrency(invoice.total, invoice.currency_code)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="invoice-cards">
      {#each recentInvoices as invoice}
        {@const effectiveStatus = getEffectiveStatus(invoice)}
        <button class="invoice-card" on:click={() => dispatch('open', invoice.id)}>
          <div class="invoice-card-header">
            <span class="invoice-card-number font-mono">#{invoice.invoice_number}</span>
            <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
              {statusConfig[effectiveStatus]?.label || effectiveStatus}
            </span>
          </div>
          <div class="invoice-card-client">{invoice.client_business || invoice.client_name || '---'}</div>
          <div class="invoice-card-footer">
            <span class="invoice-card-date">{formatDate(invoice.issue_date)}</span>
            <span class="invoice-card-total">{formatCurrency(invoice.total, invoice.currency_code)}</span>
          </div>
        </button>
      {/each}
    </div>
  {:else}
    <div class="empty-state">
      <div class="empty-state-icon">
        <Icon name="invoice" size="xl" />
      </div>
      <div class="empty-state-title">No invoices yet</div>
      <div class="empty-state-description">
        Create your first invoice to get started tracking your income.
      </div>
      <button class="btn btn-primary mt-6" on:click={() => dispatch('new')}>
        <Icon name="plus" size="sm" />
        Create Invoice
      </button>
    </div>
  {/if}
</div>

<style>
  .section {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    overflow: hidden;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--color-border-light);
  }

  .section-title {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
  }

  .section-link {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-primary);
    text-decoration: none;
  }

  .section-link:hover {
    color: var(--color-primary-hover);
  }

  .section .table-container {
    border: none;
    border-radius: 0;
  }

  .clickable-row {
    cursor: pointer;
  }

  .invoice-cards {
    display: none;
    padding: var(--space-4);
    gap: var(--space-3);
  }

  .invoice-card {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-bg);
    text-align: left;
  }

  .invoice-card-header,
  .invoice-card-footer {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    align-items: center;
  }

  .invoice-card-client,
  .invoice-card-date {
    color: var(--color-text-secondary);
  }

  .invoice-card-total {
    font-weight: 600;
  }

  .empty-state {
    text-align: center;
    padding: var(--space-12);
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
    .table-view {
      display: none;
    }

    .invoice-cards {
      display: grid;
    }
  }
</style>
