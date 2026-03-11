<script>
  export let paymentTermsDays = 30;
  export let preferredCurrency = '';
  export let notes = '';
  export let currencies = [];
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Settings</h3>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="terms" class="label">Default Payment Terms (days)</label>
      <input id="terms" type="number" class="input" min="0" bind:value={paymentTermsDays} />
      <p class="form-hint">Used as the default when creating new invoices for this client.</p>
    </div>

    <div class="form-group">
      <label for="currency" class="label">Preferred Currency</label>
      <select id="currency" class="select" bind:value={preferredCurrency}>
        <option value="">Use default (from Settings)</option>
        {#each currencies as currency}
          {#if currency.disabled}
            <option value="" disabled>{currency.name}</option>
          {:else}
            <option value={currency.code}>{currency.code} - {currency.name}</option>
          {/if}
        {/each}
      </select>
      <p class="form-hint">Pre-select this currency when creating invoices for this client.</p>
    </div>
  </div>

  <div class="form-group">
    <label for="notes" class="label">Notes</label>
    <textarea id="notes" class="textarea" rows="3" placeholder="Internal notes about this client..." bind:value={notes}></textarea>
  </div>
</div>

<style>
  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }
</style>
