<script>
  import { formatDate } from '$lib/stores';

  export let invoice = {};
  export let documentLabel = 'Invoice';
  export let isQuote = false;
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Details</h3>
  </div>
  <dl class="detail-list">
    <div class="detail-item">
      <dt>Document Type</dt>
      <dd>
        {#if isQuote}
          <span class="doc-type-badge doc-type-quote">Quote</span>
        {:else}
          <span class="doc-type-badge doc-type-invoice">Invoice</span>
        {/if}
      </dd>
    </div>
    <div class="detail-item">
      <dt>{documentLabel} Number</dt>
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

<style>
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

  .doc-type-badge {
    display: inline-flex;
    align-items: center;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .doc-type-invoice {
    background: color-mix(in srgb, var(--color-primary) 15%, transparent);
    color: var(--color-primary);
  }

  .doc-type-quote {
    background: color-mix(in srgb, var(--color-warning) 15%, transparent);
    color: var(--color-warning);
  }
</style>
