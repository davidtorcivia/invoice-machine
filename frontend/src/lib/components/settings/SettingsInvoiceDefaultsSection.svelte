<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  export let open = false;
  export let defaultPaymentTermsDays = 30;
  export let defaultCurrencyCode = 'USD';
  export let currencies = [];
  export let accentColor = '#16a34a';
  export let defaultNotes = '';
  export let defaultPaymentInstructions = '';
</script>

<CollapsibleSection title="Invoice Defaults" subtitle="Default settings for new invoices" icon="invoice" bind:open={open}>
  <div class="form-row">
    <div class="form-group">
      <label for="default-terms" class="label">Default Payment Terms (days)</label>
      <input id="default-terms" type="number" class="input" min="0" bind:value={defaultPaymentTermsDays} />
      <p class="form-hint">Default due date for new invoices.</p>
    </div>

    <div class="form-group">
      <label for="default-currency" class="label">Default Currency</label>
      <select id="default-currency" class="select" bind:value={defaultCurrencyCode}>
        {#each currencies as currency}
          {#if currency.disabled}
            <option value="" disabled>{currency.name}</option>
          {:else}
            <option value={currency.code}>{currency.code} - {currency.name}</option>
          {/if}
        {/each}
      </select>
      <p class="form-hint">Default currency for new invoices.</p>
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="accent-color" class="label">Accent Color</label>
      <div class="color-input">
        <input id="accent-color" type="color" class="color-picker" bind:value={accentColor} />
        <input type="text" class="input" bind:value={accentColor} placeholder="#16a34a" />
      </div>
      <p class="form-hint">Used for headings and accents on PDFs.</p>
    </div>
  </div>

  <div class="form-group">
    <label for="default-notes" class="label">Default Invoice Notes</label>
    <textarea
      id="default-notes"
      class="textarea"
      rows="3"
      placeholder="Thank you for your business. Payment is due within the terms specified."
      bind:value={defaultNotes}
    ></textarea>
    <p class="form-hint">This text will appear at the bottom of all new invoices.</p>
  </div>

  <div class="form-group">
    <label for="payment-instructions" class="label">Default Payment Instructions (Legacy)</label>
    <textarea
      id="payment-instructions"
      class="textarea"
      rows="4"
      placeholder="Bank: Example Bank&#10;Account: 123456789&#10;Routing: 987654321&#10;&#10;Or pay via PayPal: payments@example.com"
      bind:value={defaultPaymentInstructions}
    ></textarea>
    <p class="form-hint">Fallback text when no payment methods are selected below.</p>
  </div>
</CollapsibleSection>

<style>
  .color-input {
    display: flex;
    gap: var(--space-2);
  }

  .color-picker {
    width: 48px;
    height: 42px;
    padding: var(--space-1);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    cursor: pointer;
    background: var(--color-bg);
  }

  .color-picker::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  .color-picker::-webkit-color-swatch {
    border: none;
    border-radius: var(--radius-sm);
  }

  .color-input .input {
    flex: 1;
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  @media (max-width: 768px) {
    .color-input {
      flex-direction: column;
    }

    .color-picker {
      width: 100%;
      height: 48px;
    }
  }
</style>
