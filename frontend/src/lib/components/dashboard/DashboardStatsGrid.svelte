<script>
  import Icon from '$lib/components/Icons.svelte';
  import { formatCurrency } from '$lib/stores';

  export let stats = {
    totalOutstanding: 0,
    paidThisMonth: 0,
    draftCount: 0,
    clientCount: 0,
    currency: 'USD'
  };

  const cards = [
    { key: 'totalOutstanding', label: 'Outstanding', icon: 'dollar', tone: 'outstanding', money: true },
    { key: 'paidThisMonth', label: 'Paid This Month', icon: 'check', tone: 'paid', money: true },
    { key: 'draftCount', label: 'Draft Invoices', icon: 'pencil', tone: 'draft', money: false },
    { key: 'clientCount', label: 'Total Clients', icon: 'users', tone: 'clients', money: false }
  ];
</script>

<div class="stats-grid">
  {#each cards as card}
    <div class="stat-card">
      <div class="stat-icon stat-{card.tone}">
        <Icon name={card.icon} size="lg" />
      </div>
      <div class="stat-info">
        <div class="stat-value">{card.money ? formatCurrency(stats[card.key], stats.currency) : stats[card.key]}</div>
        <div class="stat-label">{card.label}</div>
      </div>
    </div>
  {/each}
</div>

<style>
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-6);
    margin-bottom: var(--space-8);
  }

  .stat-card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    padding: var(--space-6);
    display: flex;
    align-items: flex-start;
    gap: var(--space-4);
    transition: all var(--transition-fast);
  }

  .stat-card:hover {
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
  }

  .stat-icon {
    width: 56px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-lg);
    flex-shrink: 0;
  }

  .stat-outstanding {
    background: var(--color-primary-light);
    color: var(--color-primary);
  }

  .stat-paid {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  .stat-draft {
    background: var(--color-warning-light);
    color: var(--color-warning);
  }

  .stat-clients {
    background: var(--color-info-light);
    color: var(--color-info);
  }

  .stat-info {
    flex: 1;
    min-width: 0;
  }

  .stat-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--color-text);
    line-height: 1.2;
    margin-bottom: var(--space-1);
  }

  .stat-label {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  @media (max-width: 1024px) {
    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
      gap: var(--space-4);
    }
  }

  @media (max-width: 640px) {
    .stats-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
