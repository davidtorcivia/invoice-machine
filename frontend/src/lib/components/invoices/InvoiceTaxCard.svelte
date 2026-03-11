<script>
  export let taxEnabled = false;
  export let taxRate = '';
  export let taxName = 'Tax';
  export let checkboxLabel = 'Enable Tax';
  export let enabledHint = '';
  export let disabledHint = '';
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Tax Settings</h3>
  </div>

  <label class="checkbox-label">
    <input type="checkbox" bind:checked={taxEnabled} />
    <span>{checkboxLabel}</span>
  </label>

  {#if taxEnabled}
    <div class="form-row tax-fields">
      <div class="form-group">
        <label for="tax-rate" class="label">Tax Rate (%)</label>
        <input
          id="tax-rate"
          type="number"
          class="input"
          min="0"
          max="100"
          step="0.01"
          placeholder="e.g. 10"
          bind:value={taxRate}
        />
      </div>

      <div class="form-group">
        <label for="tax-name" class="label">Tax Name</label>
        <input
          id="tax-name"
          type="text"
          class="input"
          placeholder="e.g. VAT, GST, Sales Tax"
          bind:value={taxName}
        />
      </div>
    </div>
    {#if enabledHint}
      <p class="form-hint">{enabledHint}</p>
    {/if}
  {:else if disabledHint}
    <p class="form-hint">{disabledHint}</p>
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

  .tax-fields {
    margin-top: var(--space-4);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }
</style>
