<script>
  export let taxOverride = false;
  export let taxEnabled = false;
  export let taxRate = '';
  export let taxName = 'Tax';
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Tax Settings</h3>
  </div>

  <label class="checkbox-label">
    <input type="checkbox" bind:checked={taxOverride} />
    <span>Override global tax settings for this client</span>
  </label>
  <p class="form-hint">When unchecked, invoices for this client will use your global default tax settings.</p>

  {#if taxOverride}
    <div class="tax-override-section">
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={taxEnabled} />
        <span>Enable Tax</span>
      </label>

      {#if taxEnabled}
        <div class="form-row tax-fields">
          <div class="form-group">
            <label for="tax-rate" class="label">Tax Rate (%)</label>
            <input id="tax-rate" type="number" class="input" min="0" max="100" step="0.01" placeholder="e.g. 10" bind:value={taxRate} />
          </div>
          <div class="form-group">
            <label for="tax-name" class="label">Tax Name</label>
            <input id="tax-name" type="text" class="input" placeholder="e.g. VAT, GST, Sales Tax" bind:value={taxName} />
          </div>
        </div>
      {:else}
        <p class="form-hint disabled-hint">Tax will be disabled for invoices to this client.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 500;
  }

  .checkbox-label input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  .tax-override-section {
    margin-top: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
  }

  .tax-fields {
    margin-top: var(--space-4);
  }

  .disabled-hint {
    margin-top: var(--space-3);
  }
</style>
