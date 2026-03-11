<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { getAvatarColor } from '$lib/clients/config';

  export let client = {};

  const dispatch = createEventDispatcher();

  $: avatar = getAvatarColor(client.id);
</script>

<div class="client-card" on:click={() => dispatch('open', client.id)} role="button" tabindex="0" on:keydown={(event) => event.key === 'Enter' && dispatch('open', client.id)}>
  <div class="client-card-header">
    <div class="client-avatar" style="background-color: {avatar.bg}; color: {avatar.fg};">
      {(client.business_name || client.name || '?').charAt(0).toUpperCase()}
    </div>
    <div class="client-identity">
      <h3 class="client-name">{client.business_name || client.name}</h3>
      {#if client.business_name && client.name}
        <p class="client-contact">{client.name}</p>
      {/if}
    </div>
    <div class="client-actions">
      <button class="btn btn-ghost btn-icon btn-sm" on:click={(event) => { event.stopPropagation(); dispatch('edit', client.id); }} title="Edit">
        <Icon name="pencil" size="sm" />
      </button>
      <button class="btn btn-ghost btn-icon btn-sm" on:click={(event) => { event.stopPropagation(); dispatch('delete', client); }} title="Delete">
        <Icon name="trash" size="sm" />
      </button>
    </div>
  </div>

  <div class="client-details">
    {#if client.email}
      <div class="client-field">
        <Icon name="mail" size="sm" />
        <span>{client.email}</span>
      </div>
    {/if}
    {#if client.phone}
      <div class="client-field">
        <Icon name="phone" size="sm" />
        <span>{client.phone}</span>
      </div>
    {/if}
    {#if client.city || client.state}
      <div class="client-field">
        <Icon name="location" size="sm" />
        <span>{[client.city, client.state].filter(Boolean).join(', ')}</span>
      </div>
    {/if}
  </div>

  <div class="client-footer">
    <span class="payment-terms">Net {client.payment_terms_days || 30} days</span>
  </div>
</div>

<style>
  .client-card {
    cursor: pointer;
  }

  .client-card-header {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .client-avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    flex-shrink: 0;
  }

  .client-identity {
    min-width: 0;
    flex: 1;
  }

  .client-name {
    margin: 0;
  }

  .client-contact {
    margin: var(--space-1) 0 0;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .client-actions {
    display: flex;
    gap: var(--space-1);
  }

  .client-details {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-4);
  }

  .client-field {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .client-footer {
    margin-top: var(--space-4);
  }

  .payment-terms {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }
</style>
