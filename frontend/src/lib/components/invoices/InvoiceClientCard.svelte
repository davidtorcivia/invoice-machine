<script>
  import Icon from '$lib/components/Icons.svelte';

  export let invoice = {};
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Bill To</h3>
  </div>
  <div class="client-info">
    {#if invoice.client_business}
      <div class="client-business">{invoice.client_business}</div>
    {/if}
    {#if invoice.client_name}
      <div class="client-contact">Attn: {invoice.client_name}</div>
    {/if}
    {#if invoice.client_address}
      <div class="client-address">{invoice.client_address}</div>
    {/if}
    {#if invoice.client_email}
      <div class="client-email">
        <Icon name="mail" size="sm" />
        {invoice.client_email}
      </div>
    {/if}
  </div>
</div>

<style>
  .client-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .client-business {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .client-contact {
    color: var(--color-text-secondary);
  }

  .client-address {
    white-space: pre-line;
    color: var(--color-text-secondary);
    line-height: 1.5;
  }

  .client-email {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-primary);
    margin-top: var(--space-2);
  }
</style>
