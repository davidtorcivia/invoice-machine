<script>
  import Icon from '$lib/components/Icons.svelte';
  import { formatCurrency } from '$lib/stores';

  /** @typedef {{ description: string, quantity: number, unit_price: string | number, unit_type: string }} InvoiceItemDraft */

  /** @type {InvoiceItemDraft[]} */
  export let items = [];
  export let taxEnabled = false;
  export let taxRate = '';
  export let taxName = 'Tax';
  export let addButtonText = 'Add Item';
  export let currencyCode = 'USD';

  // Round to cents per line so this live preview matches the backend's
  // decimal arithmetic (the server is authoritative on save).
  const round2 = (n) => Math.round((Number(n) || 0) * 100) / 100;

  function addItem() {
    items = [...items, { description: '', quantity: 1, unit_price: '', unit_type: 'qty' }];
  }

  function removeItem(index) {
    if (items.length > 1) {
      items = items.filter((_, i) => i !== index);
    }
  }

  $: subtotal = round2(
    items.reduce((sum, item) => sum + round2((Number(item.unit_price) || 0) * item.quantity), 0)
  );
  $: parsedTaxRate = Number(taxRate) || 0;
  $: taxAmount = taxEnabled && parsedTaxRate > 0 ? round2(subtotal * parsedTaxRate / 100) : 0;
  $: total = round2(subtotal + taxAmount);
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Line Items</h3>
    <button type="button" class="btn btn-secondary btn-sm" on:click={addItem}>
      <Icon name="plus" size="sm" />
      {addButtonText}
    </button>
  </div>

  <div class="items-list">
    {#each items as item, index}
      <div class="item-row">
        <div class="item-fields">
          <div class="form-group item-desc">
            <label class="label" for={`item-desc-${index}`}>Description</label>
            <input
              id={`item-desc-${index}`}
              type="text"
              class="input"
              placeholder="Service or product description"
              bind:value={item.description}
            />
          </div>

          <div class="form-group item-unit-type">
            <label class="label" for={`item-unit-type-${index}`}>Type</label>
            <select id={`item-unit-type-${index}`} class="select" bind:value={item.unit_type}>
              <option value="qty">Qty</option>
              <option value="hours">Hours</option>
            </select>
          </div>

          <div class="form-group item-qty">
            <label class="label" for={`item-qty-${index}`}>{item.unit_type === 'hours' ? 'Hours' : 'Qty'}</label>
            <input
              id={`item-qty-${index}`}
              type="number"
              class="input"
              min="1"
              step={item.unit_type === 'hours' ? '0.5' : '1'}
              bind:value={item.quantity}
            />
          </div>

          <div class="form-group item-price">
            <label class="label" for={`item-price-${index}`}>{item.unit_type === 'hours' ? 'Rate' : 'Price'}</label>
            <input
              id={`item-price-${index}`}
              type="number"
              class="input"
              step="0.01"
              min="0"
              placeholder="0.00"
              bind:value={item.unit_price}
            />
          </div>

          <div class="form-group item-total">
            <div class="label">Total</div>
            <div class="item-total-value">
              {formatCurrency(round2((Number(item.unit_price) || 0) * item.quantity), currencyCode)}
            </div>
          </div>
        </div>

        <button
          type="button"
          class="btn btn-ghost btn-icon btn-sm btn-remove"
          on:click={() => removeItem(index)}
          disabled={items.length === 1}
          title="Remove item"
        >
          <Icon name="x" size="sm" />
        </button>
      </div>
    {/each}
  </div>

  <div class="totals-summary">
    <div class="totals-rows">
      <div class="total-row">
        <span class="totals-label">Subtotal</span>
        <span class="totals-value">{formatCurrency(subtotal, currencyCode)}</span>
      </div>
      {#if taxEnabled && parsedTaxRate > 0}
        <div class="total-row tax-row">
          <span class="totals-label">{taxName || 'Tax'} ({taxRate}%)</span>
          <span class="totals-value">{formatCurrency(taxAmount, currencyCode)}</span>
        </div>
      {/if}
      <div class="total-row total-final">
        <span class="totals-label">Total</span>
        <span class="totals-value totals-total">{formatCurrency(total, currencyCode)}</span>
      </div>
    </div>
  </div>
</div>

<style>
  .items-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .item-row {
    display: flex;
    gap: var(--space-3);
    align-items: flex-start;
  }

  .item-fields {
    display: flex;
    gap: var(--space-3);
    flex: 1;
    flex-wrap: wrap;
  }

  .item-desc {
    flex: 2;
    min-width: 200px;
  }

  .item-unit-type {
    flex: 0 0 80px;
  }

  .item-qty {
    flex: 0 0 80px;
  }

  .item-price {
    flex: 0 0 120px;
  }

  .item-total {
    flex: 0 0 100px;
  }

  .item-total-value {
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    font-weight: 500;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .btn-remove {
    margin-top: 28px;
    color: var(--color-text-tertiary);
  }

  .btn-remove:hover:not(:disabled) {
    color: var(--color-danger);
  }

  .btn-remove:disabled {
    opacity: 0.3;
  }

  .totals-summary {
    display: flex;
    justify-content: flex-end;
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
    margin-top: var(--space-4);
  }

  .totals-rows {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 200px;
  }

  .total-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-6);
  }

  .totals-label {
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .totals-value {
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  .tax-row {
    color: var(--color-text-tertiary);
    font-size: 0.9375rem;
  }

  .total-final {
    padding-top: var(--space-2);
    border-top: 1px solid var(--color-border-light);
    margin-top: var(--space-1);
  }

  .totals-total {
    font-size: 1.125rem;
    font-weight: 600;
  }

  @media (min-width: 1400px) {
    .item-desc {
      flex: 3;
      min-width: 300px;
    }

    .item-unit-type {
      flex: 0 0 100px;
    }

    .item-qty {
      flex: 0 0 100px;
    }

    .item-price {
      flex: 0 0 140px;
    }

    .item-total {
      flex: 0 0 130px;
    }
  }

  @media (max-width: 768px) {
    .item-fields {
      flex-direction: column;
    }

    .item-desc,
    .item-unit-type,
    .item-qty,
    .item-price,
    .item-total {
      flex: 1;
      min-width: 100%;
    }

    .btn-remove {
      margin-top: 0;
      align-self: flex-end;
    }
  }
</style>
