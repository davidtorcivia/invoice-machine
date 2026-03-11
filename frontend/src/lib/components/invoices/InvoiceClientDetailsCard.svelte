<script>
  import Icon from '$lib/components/Icons.svelte';
  import { currencies } from '$lib/data/currencies';

  export let clients = [];
  export let clientId = '';
  export let issueDate = '';
  export let paymentTermsDays = 30;
  export let currencyCode = 'USD';
  export let clientReference = '';
  export let invoiceNumberOverride = '';
  export let isQuote = false;
  export let openClientModal;
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Client & Dates</h3>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="client" class="label">Client *</label>
      <div class="client-select-wrapper">
        <select id="client" class="select" bind:value={clientId} required>
          <option value="">Select a client...</option>
          {#each clients as client}
            <option value={client.id}>{client.business_name || client.name}</option>
          {/each}
        </select>
        <button type="button" class="btn btn-secondary btn-sm new-client-btn" on:click={openClientModal}>
          <Icon name="plus" size="sm" />
          New
        </button>
      </div>
    </div>

    <div class="form-group">
      <label for="issue-date" class="label">Issue Date</label>
      <input id="issue-date" type="date" class="input" bind:value={issueDate} />
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="terms" class="label">Payment Terms (days)</label>
      <input id="terms" type="number" class="input" min="0" bind:value={paymentTermsDays} />
    </div>

    <div class="form-group">
      <label for="currency" class="label">Currency</label>
      <select id="currency" class="select" bind:value={currencyCode}>
        {#each currencies as currency}
          {#if currency.disabled}
            <option value="" disabled>{currency.name}</option>
          {:else}
            <option value={currency.code}>{currency.code} - {currency.name}</option>
          {/if}
        {/each}
      </select>
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="client-ref" class="label">Client Reference / PO Number</label>
      <input id="client-ref" type="text" class="input" placeholder="PO-12345" bind:value={clientReference} />
    </div>

    <div class="form-group">
      <label for="invoice-number" class="label">{isQuote ? 'Quote' : 'Invoice'} Number Override</label>
      <input id="invoice-number" type="text" class="input" placeholder="Auto-generated" bind:value={invoiceNumberOverride} />
      <p class="form-hint">Leave blank for automatic numbering.</p>
    </div>
  </div>
</div>

<style>
  .client-select-wrapper {
    display: flex;
    gap: var(--space-2);
  }

  .client-select-wrapper .select {
    flex: 1;
  }

  .new-client-btn {
    flex-shrink: 0;
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  @media (max-width: 768px) {
    .client-select-wrapper {
      flex-direction: column;
    }
  }
</style>
