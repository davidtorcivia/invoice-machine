<script>
  import { getBarWidth } from '$lib/reports/format';

  export let clientData = [];

  $: maxPaid = clientData.length
    ? Math.max(...clientData.map((client) => parseFloat(client.total_paid)))
    : 0;
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Top Clients by Revenue</h3>
  </div>

  {#if clientData.length > 0}
    <div class="clients-list">
      {#each clientData as client, index}
        <div class="client-row">
          <div class="client-rank">{index + 1}</div>
          <div class="client-info">
            <span class="client-name">{client.name}</span>
            <span class="client-stats">
              {client.invoice_count} invoice{client.invoice_count !== 1 ? 's' : ''}
              {#if client.first_invoice}
                &middot; since {new Date(client.first_invoice).getFullYear()}
              {/if}
            </span>
          </div>
          <div class="client-revenue">
            <div class="revenue-bar-container">
              <div class="revenue-bar" style="width: {getBarWidth(client.total_paid, maxPaid)}%"></div>
            </div>
            <span class="revenue-value">{client.total_paid_formatted}</span>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty-clients">
      <p>No client data available</p>
    </div>
  {/if}
</div>

<style>
  .card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-6);
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid var(--color-border);
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .card-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .clients-list {
    padding: var(--space-4);
  }

  .client-row {
    display: grid;
    grid-template-columns: 32px 1fr 180px;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--color-border);
  }

  .client-row:last-child {
    border-bottom: none;
  }

  .client-rank {
    width: 24px;
    height: 24px;
    border-radius: var(--radius-full);
    background: var(--color-bg-sunken);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--color-text-secondary);
  }

  .client-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .client-name {
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .client-stats {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }

  .client-revenue {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-1);
  }

  .revenue-bar-container {
    width: 100%;
    height: 6px;
    background: var(--color-bg-sunken);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .revenue-bar {
    height: 100%;
    background: var(--color-success);
    border-radius: var(--radius-full);
    transition: width 0.3s ease;
  }

  .revenue-value {
    font-size: 0.875rem;
    font-weight: 600;
  }

  .empty-clients {
    padding: var(--space-8);
    text-align: center;
    color: var(--color-text-secondary);
  }

  @media (max-width: 768px) {
    .client-row {
      grid-template-columns: 24px 1fr;
    }

    .client-revenue {
      grid-column: 1 / -1;
      align-items: stretch;
    }
  }
</style>
