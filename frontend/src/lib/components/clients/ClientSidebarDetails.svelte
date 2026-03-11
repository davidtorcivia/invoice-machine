<script>
  import Icon from '$lib/components/Icons.svelte';

  export let client = {};
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Contact Information</h3>
  </div>

  <div class="contact-info">
    {#if client.email}
      <a href="mailto:{client.email}" class="contact-item">
        <Icon name="mail" size="sm" />
        <span>{client.email}</span>
      </a>
    {/if}
    {#if client.phone}
      <a href="tel:{client.phone}" class="contact-item">
        <Icon name="phone" size="sm" />
        <span>{client.phone}</span>
      </a>
    {/if}
    {#if client.address_line1 || client.city || client.state}
      <div class="contact-item">
        <Icon name="location" size="sm" />
        <div class="address">
          {#if client.address_line1}<div>{client.address_line1}</div>{/if}
          {#if client.address_line2}<div>{client.address_line2}</div>{/if}
          {#if client.city || client.state || client.postal_code}
            <div>{[client.city, client.state].filter(Boolean).join(', ')} {client.postal_code || ''}</div>
          {/if}
          {#if client.country}<div>{client.country}</div>{/if}
        </div>
      </div>
    {/if}
  </div>

  {#if !client.email && !client.phone && !client.address_line1}
    <p class="text-secondary text-sm">No contact information added.</p>
  {/if}
</div>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Settings</h3>
  </div>
  <dl class="detail-list">
    <div class="detail-item">
      <dt>Payment Terms</dt>
      <dd>Net {client.payment_terms_days || 30} days</dd>
    </div>
    <div class="detail-item">
      <dt>Tax Settings</dt>
      {#if client.tax_enabled !== null}
        <dd>
          {#if client.tax_enabled}
            <span class="tax-badge tax-enabled">{client.tax_name || 'Tax'} @ {client.tax_rate || 0}%</span>
          {:else}
            <span class="tax-badge tax-disabled">Tax Disabled</span>
          {/if}
        </dd>
      {:else}
        <dd class="text-secondary">Using global default</dd>
      {/if}
    </div>
    {#if client.notes}
      <div class="detail-item">
        <dt>Notes</dt>
        <dd class="notes-text">{client.notes}</dd>
      </div>
    {/if}
  </dl>
</div>

<style>
  .contact-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .contact-item {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    color: var(--color-text);
    text-decoration: none;
  }

  .contact-item:hover {
    color: var(--color-primary);
  }

  .contact-item :global(.icon) {
    color: var(--color-text-tertiary);
    flex-shrink: 0;
    margin-top: 2px;
  }

  .address {
    line-height: 1.5;
  }

  .detail-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .detail-item {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .detail-item dt {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .detail-item dd {
    font-weight: 500;
    color: var(--color-text);
  }

  .notes-text {
    font-weight: 400;
    white-space: pre-line;
    line-height: 1.5;
  }

  .tax-badge {
    display: inline-flex;
    align-items: center;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm);
    font-size: 0.8125rem;
    font-weight: 500;
  }

  .tax-enabled {
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-success);
  }

  .tax-disabled {
    background: color-mix(in srgb, var(--color-text-tertiary) 15%, transparent);
    color: var(--color-text-tertiary);
  }
</style>
