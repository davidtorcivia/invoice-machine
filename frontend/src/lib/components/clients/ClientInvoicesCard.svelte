<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { formatDate, formatCurrency } from '$lib/stores';
  import { statusConfig } from '$lib/invoices/list';

  export let invoices = [];

  const dispatch = createEventDispatcher();
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Invoices</h3>
    <button class="btn btn-secondary btn-sm" on:click={() => dispatch('newinvoice')}>
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
            <tr on:click={() => dispatch('openinvoice', invoice.id)} class="clickable-row">
              <td><span class="invoice-number font-mono">#{invoice.invoice_number}</span></td>
              <td class="text-secondary">{formatDate(invoice.issue_date)}</td>
              <td class="text-secondary">{invoice.due_date ? formatDate(invoice.due_date) : '---'}</td>
              <td>
                <span class="badge {statusConfig[invoice.status]?.class || 'badge-draft'}">
                  {statusConfig[invoice.status]?.label || invoice.status}
                </span>
              </td>
              <td class="text-right"><span class="invoice-total">{formatCurrency(invoice.total)}</span></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="empty-state-small">
      <Icon name="invoice" size="lg" />
      <p>No invoices yet</p>
      <button class="btn btn-primary btn-sm" on:click={() => dispatch('newinvoice')}>Create Invoice</button>
    </div>
  {/if}
</div>

<style>
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

  @media (max-width: 640px) {
    .table th:nth-child(3),
    .table td:nth-child(3) {
      display: none;
    }
  }

  @media (max-width: 480px) {
    .table th:nth-child(2),
    .table td:nth-child(2) {
      display: none;
    }
  }
</style>
