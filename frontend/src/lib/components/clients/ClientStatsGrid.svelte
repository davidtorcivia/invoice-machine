<script>
  import { formatCurrency } from '$lib/stores';

  export let invoices = [];

  // Quotes are not billed amounts, and money is never summed across currencies.
  // Restrict to invoice documents in the client's dominant currency; per-currency
  // reporting lives in the analytics endpoints.
  $: invoiceDocs = invoices.filter((invoice) => (invoice.document_type || 'invoice') === 'invoice');
  $: currency = invoiceDocs.find((invoice) => invoice.currency_code)?.currency_code || 'USD';
  $: scoped = invoiceDocs.filter((invoice) => (invoice.currency_code || 'USD') === currency);
  // "Billed" = issued invoices (sent/paid/overdue), matching the backend; drafts
  // and cancelled invoices are excluded.
  $: totalBilled = scoped
    .filter((invoice) => ['sent', 'paid', 'overdue'].includes(invoice.status))
    .reduce((sum, invoice) => sum + parseFloat(invoice.total || 0), 0);
  $: totalPaid = scoped.filter((invoice) => invoice.status === 'paid').reduce((sum, invoice) => sum + parseFloat(invoice.total || 0), 0);
  $: totalOutstanding = scoped
    .filter((invoice) => invoice.status === 'sent' || invoice.status === 'overdue')
    .reduce((sum, invoice) => sum + parseFloat(invoice.total || 0), 0);
</script>

<div class="stats-row">
  <div class="stat-card">
    <div class="stat-label">Total Billed</div>
    <div class="stat-value">{formatCurrency(totalBilled, currency)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Total Paid</div>
    <div class="stat-value stat-success">{formatCurrency(totalPaid, currency)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Outstanding</div>
    <div class="stat-value stat-warning">{formatCurrency(totalOutstanding, currency)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Invoices</div>
    <div class="stat-value">{invoiceDocs.length}</div>
  </div>
</div>

<style>
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

  @media (max-width: 1024px) {
    .stats-row {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 768px) {
    .stats-row {
      grid-template-columns: 1fr;
    }
  }
</style>
