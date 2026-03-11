<script>
  import { formatCurrency } from '$lib/stores';

  export let invoice = {};
  export let items = [];
</script>

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
          {#each items as item}
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
      {#if invoice.tax_enabled && parseFloat(invoice.tax_amount) > 0}
        <div class="total-row tax-row">
          <span class="total-label">{invoice.tax_name || 'Tax'} ({invoice.tax_rate}%)</span>
          <span class="total-value">{formatCurrency(invoice.tax_amount)}</span>
        </div>
      {/if}
      <div class="total-row total-final">
        <span class="total-label">Total</span>
        <span class="total-value total-amount">{formatCurrency(invoice.total)}</span>
      </div>
    </div>
  {:else}
    <p class="text-secondary">No line items.</p>
  {/if}
</div>

<style>
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

  .tax-row .total-label {
    color: var(--color-text-tertiary);
  }

  .tax-row .total-value {
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

  @media (max-width: 480px) {
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
