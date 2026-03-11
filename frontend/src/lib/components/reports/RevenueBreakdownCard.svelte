<script>
  import Icon from '$lib/components/Icons.svelte';
  import { getBarWidth } from '$lib/reports/format';

  /** @type {{ breakdown?: Array<{ period: string, invoiced: string | number, paid: string | number, invoiced_formatted: string, paid_formatted: string }> } | null} */
  export let revenueData = null;
  export let year = new Date().getFullYear();
  export let groupBy = 'month';
  export let changeYear;
  export let changeGroupBy;

  /** @type {Array<{ period: string, invoiced: string | number, paid: string | number, invoiced_formatted: string, paid_formatted: string }>} */
  $: breakdown = revenueData?.breakdown || [];
  $: maxInvoiced = breakdown.length
    ? Math.max(...breakdown.map((period) => Number(period.invoiced)))
    : 0;
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Revenue by Period</h3>
    <div class="card-controls">
      <div class="year-nav">
        <button class="btn btn-ghost btn-sm" on:click={() => changeYear(-1)}>
          <Icon name="chevronLeft" size="sm" />
        </button>
        <span class="year-label">{year}</span>
        <button class="btn btn-ghost btn-sm" on:click={() => changeYear(1)} disabled={year >= new Date().getFullYear()}>
          <Icon name="chevronRight" size="sm" />
        </button>
      </div>

      <div class="group-tabs">
        <button class="tab" class:active={groupBy === 'month'} on:click={() => changeGroupBy('month')}>Monthly</button>
        <button class="tab" class:active={groupBy === 'quarter'} on:click={() => changeGroupBy('quarter')}>Quarterly</button>
      </div>
    </div>
  </div>

  {#if breakdown.length > 0}
    <div class="breakdown-chart">
      {#each breakdown as period}
        <div class="chart-row">
          <span class="chart-label">{period.period}</span>
          <div class="chart-bars">
            <div class="bar-container">
              <div class="bar bar-invoiced" style="width: {getBarWidth(period.invoiced, maxInvoiced)}%"></div>
            </div>
            <div class="bar-container">
              <div class="bar bar-paid" style="width: {getBarWidth(period.paid, maxInvoiced)}%"></div>
            </div>
          </div>
          <div class="chart-values">
            <span class="value-invoiced">{period.invoiced_formatted}</span>
            <span class="value-paid">{period.paid_formatted}</span>
          </div>
        </div>
      {/each}
    </div>

    <div class="chart-legend">
      <div class="legend-item">
        <span class="legend-dot invoiced"></span>
        <span>Invoiced</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot paid"></span>
        <span>Paid</span>
      </div>
    </div>
  {:else}
    <div class="empty-chart">
      <p>No invoice data for {year}</p>
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

  .card-controls {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .year-nav {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .year-label {
    font-weight: 600;
    min-width: 50px;
    text-align: center;
  }

  .group-tabs {
    display: flex;
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    padding: 2px;
  }

  .tab {
    padding: var(--space-2) var(--space-3);
    font-size: 0.8125rem;
    font-weight: 500;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    color: var(--color-text-secondary);
    transition: all var(--transition-fast);
  }

  .tab:hover {
    color: var(--color-text);
  }

  .tab.active {
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-sm);
  }

  .breakdown-chart {
    padding: var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .chart-row {
    display: grid;
    grid-template-columns: 80px 1fr 120px;
    gap: var(--space-3);
    align-items: center;
  }

  .chart-label {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .chart-bars {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .bar-container {
    height: 8px;
    background: var(--color-bg-sunken);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .bar {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 0.3s ease;
  }

  .bar-invoiced {
    background: var(--color-primary);
  }

  .bar-paid {
    background: var(--color-success);
  }

  .chart-values {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    font-size: 0.75rem;
    gap: 2px;
  }

  .value-invoiced {
    color: var(--color-primary);
    font-weight: 500;
  }

  .value-paid {
    color: var(--color-success);
    font-weight: 500;
  }

  .chart-legend {
    display: flex;
    justify-content: center;
    gap: var(--space-4);
    padding: var(--space-3);
    border-top: 1px solid var(--color-border);
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
  }

  .legend-dot.invoiced {
    background: var(--color-primary);
  }

  .legend-dot.paid {
    background: var(--color-success);
  }

  .empty-chart {
    padding: var(--space-8);
    text-align: center;
    color: var(--color-text-secondary);
  }
</style>
