<script>
  import Icon from '$lib/components/Icons.svelte';
  import { reportSummaryCards } from '$lib/reports/format';

  export let totals = {};
</script>

<div class="summary-grid">
  {#each reportSummaryCards as card}
    <div class="summary-card">
      <div class="summary-icon {card.tone}">
        <Icon name={card.icon} size="md" />
      </div>
      <div class="summary-content">
        <span class="summary-label">{card.label}</span>
        <span class="summary-value">{totals?.[`${card.key}_formatted`] || '$0'}</span>
      </div>
    </div>
  {/each}
</div>

<style>
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-4);
    margin-bottom: var(--space-6);
  }

  .summary-card {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-5);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .summary-icon {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .summary-icon.invoiced {
    background: var(--color-primary-light);
    color: var(--color-primary);
  }

  .summary-icon.paid {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  .summary-icon.outstanding {
    background: var(--color-warning-light);
    color: var(--color-warning);
  }

  .summary-icon.overdue {
    background: var(--color-danger-light);
    color: var(--color-danger);
  }

  .summary-content {
    display: flex;
    flex-direction: column;
  }

  .summary-label {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .summary-value {
    font-size: 1.375rem;
    font-weight: 700;
    color: var(--color-text);
  }
</style>
