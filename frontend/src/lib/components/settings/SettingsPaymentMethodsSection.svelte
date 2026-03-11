<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let open = false;
  export let paymentMethods = [];
  export let openAddMethodModal;
  export let openEditMethodModal;
  export let deletePaymentMethod;
</script>

<CollapsibleSection title="Payment Methods" subtitle="Configure payment options" icon="invoice" bind:open={open}>
  <div class="section-header-actions">
    <button type="button" class="btn btn-secondary btn-sm" on:click={openAddMethodModal}>
      <Icon name="plus" size="sm" />
      Add Method
    </button>
  </div>

  <p class="form-hint mb-4">Configure payment options your clients can use. Select which methods to show on each invoice.</p>

  {#if paymentMethods.length > 0}
    <div class="payment-methods-list">
      {#each paymentMethods as method}
        <div class="payment-method-item">
          <div class="payment-method-info">
            <span class="payment-method-name">{method.name}</span>
            {#if method.instructions}
              <span class="payment-method-preview">{method.instructions.substring(0, 60)}{method.instructions.length > 60 ? '...' : ''}</span>
            {/if}
          </div>
          <div class="payment-method-actions">
            <button type="button" class="btn btn-ghost btn-icon btn-sm" on:click={() => openEditMethodModal(method)} title="Edit">
              <Icon name="pencil" size="sm" />
            </button>
            <button type="button" class="btn btn-ghost btn-icon btn-sm" on:click={() => deletePaymentMethod(method.id)} title="Delete">
              <Icon name="trash" size="sm" />
            </button>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty-methods">
      <p class="text-secondary">No payment methods configured yet.</p>
      <button type="button" class="btn btn-secondary btn-sm mt-2" on:click={openAddMethodModal}>
        <Icon name="plus" size="sm" />
        Add your first method
      </button>
    </div>
  {/if}
</CollapsibleSection>

<style>
  .section-header-actions {
    display: flex;
    justify-content: flex-end;
    margin-bottom: var(--space-4);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  .mb-4 {
    margin-bottom: var(--space-4);
  }

  .payment-methods-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .payment-method-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-4);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .payment-method-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
    flex: 1;
  }

  .payment-method-name {
    font-weight: 500;
    color: var(--color-text);
  }

  .payment-method-preview {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    white-space: pre-wrap;
    line-height: 1.4;
  }

  .payment-method-actions {
    display: flex;
    gap: var(--space-1);
    flex-shrink: 0;
  }

  .empty-methods {
    text-align: center;
    padding: var(--space-6);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
  }

  .mt-2 {
    margin-top: var(--space-2);
  }
</style>
