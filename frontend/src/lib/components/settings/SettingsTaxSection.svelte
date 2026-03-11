<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  export let open = false;
  export let defaultTaxEnabled = false;
  export let defaultTaxName = 'Tax';
  export let defaultTaxRate = '';
</script>

<CollapsibleSection title="Tax Settings" subtitle="Default tax configuration" icon="invoice" bind:open={open}>
  <p class="form-hint mb-4">
    Configure default tax settings for new invoices. These can be overridden on individual invoices.
  </p>

  <div class="form-group">
    <label class="toggle-container">
      <input type="checkbox" bind:checked={defaultTaxEnabled} />
      <span class="toggle-label">Enable tax by default on new invoices</span>
    </label>
  </div>

  {#if defaultTaxEnabled}
    <div class="form-row">
      <div class="form-group">
        <label for="tax-name" class="label">Tax Name</label>
        <input id="tax-name" type="text" class="input" placeholder="Tax" bind:value={defaultTaxName} />
        <p class="form-hint">e.g., "Sales Tax", "VAT", "GST"</p>
      </div>

      <div class="form-group">
        <label for="tax-rate" class="label">Tax Rate (%)</label>
        <input
          id="tax-rate"
          type="number"
          class="input"
          placeholder="0.00"
          step="0.01"
          min="0"
          max="100"
          bind:value={defaultTaxRate}
        />
        <p class="form-hint">Default tax percentage</p>
      </div>
    </div>
  {/if}
</CollapsibleSection>

<style>
  .mb-4 {
    margin-bottom: var(--space-4);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  .toggle-container {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    user-select: none;
  }

  .toggle-container input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
    cursor: pointer;
  }

  .toggle-label {
    font-size: 0.9375rem;
    color: var(--color-text);
  }
</style>
