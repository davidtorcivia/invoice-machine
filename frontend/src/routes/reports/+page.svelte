<script>
  import { onMount } from 'svelte';
  import { analyticsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let loading = true;
  let revenueData = null;
  let clientData = [];

  // Filters
  let groupBy = 'month';
  let year = new Date().getFullYear();

  $: fromDate = `${year}-01-01`;
  $: toDate = `${year}-12-31`;

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const [revenue, clients] = await Promise.all([
        analyticsApi.getRevenue({ from_date: fromDate, to_date: toDate, group_by: groupBy }),
        analyticsApi.getClientLifetimeValues({ limit: 10 })
      ]);
      revenueData = revenue;
      clientData = clients;
    } catch (error) {
      toast.error('Failed to load analytics');
      console.error(error);
    } finally {
      loading = false;
    }
  }

  async function changeYear(delta) {
    year += delta;
    await loadData();
  }

  async function changeGroupBy(newGroupBy) {
    groupBy = newGroupBy;
    await loadData();
  }

  function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(parseFloat(amount) || 0);
  }

  function getBarWidth(value, max) {
    if (!max || max === 0) return 0;
    return Math.min((parseFloat(value) / parseFloat(max)) * 100, 100);
  }
</script>

<Header title="Reports" subtitle="Revenue analytics and client insights" />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <!-- Summary Cards -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-icon invoiced">
          <Icon name="invoice" size="md" />
        </div>
        <div class="summary-content">
          <span class="summary-label">Total Invoiced</span>
          <span class="summary-value">{revenueData?.totals?.invoiced_formatted || '$0'}</span>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-icon paid">
          <Icon name="check" size="md" />
        </div>
        <div class="summary-content">
          <span class="summary-label">Total Paid</span>
          <span class="summary-value">{revenueData?.totals?.paid_formatted || '$0'}</span>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-icon outstanding">
          <Icon name="clock" size="md" />
        </div>
        <div class="summary-content">
          <span class="summary-label">Outstanding</span>
          <span class="summary-value">{revenueData?.totals?.outstanding_formatted || '$0'}</span>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-icon overdue">
          <Icon name="warning" size="md" />
        </div>
        <div class="summary-content">
          <span class="summary-label">Overdue</span>
          <span class="summary-value">{revenueData?.totals?.overdue_formatted || '$0'}</span>
        </div>
      </div>
    </div>

    <!-- Revenue Breakdown -->
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
            <button
              class="tab"
              class:active={groupBy === 'month'}
              on:click={() => changeGroupBy('month')}
            >
              Monthly
            </button>
            <button
              class="tab"
              class:active={groupBy === 'quarter'}
              on:click={() => changeGroupBy('quarter')}
            >
              Quarterly
            </button>
          </div>
        </div>
      </div>

      {#if revenueData?.breakdown?.length > 0}
        {@const maxInvoiced = Math.max(...revenueData.breakdown.map(b => parseFloat(b.invoiced)))}
        <div class="breakdown-chart">
          {#each revenueData.breakdown as period}
            <div class="chart-row">
              <span class="chart-label">{period.period}</span>
              <div class="chart-bars">
                <div class="bar-container">
                  <div
                    class="bar bar-invoiced"
                    style="width: {getBarWidth(period.invoiced, maxInvoiced)}%"
                  ></div>
                </div>
                <div class="bar-container">
                  <div
                    class="bar bar-paid"
                    style="width: {getBarWidth(period.paid, maxInvoiced)}%"
                  ></div>
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

    <!-- Top Clients -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Top Clients by Revenue</h3>
      </div>

      {#if clientData.length > 0}
        {@const maxPaid = Math.max(...clientData.map(c => parseFloat(c.total_paid)))}
        <div class="clients-list">
          {#each clientData as client, i}
            <div class="client-row">
              <div class="client-rank">{i + 1}</div>
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
                  <div
                    class="revenue-bar"
                    style="width: {getBarWidth(client.total_paid, maxPaid)}%"
                  ></div>
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
  {/if}
</div>

<style>
  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-10);
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Summary Cards */
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

  /* Card */
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

  /* Revenue Chart */
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

  .empty-chart,
  .empty-clients {
    padding: var(--space-8);
    text-align: center;
    color: var(--color-text-secondary);
  }

  /* Clients List */
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
    color: var(--color-success);
  }

  @media (max-width: 640px) {
    .chart-row {
      grid-template-columns: 60px 1fr 80px;
    }

    .client-row {
      grid-template-columns: 24px 1fr;
    }

    .client-revenue {
      grid-column: 2;
      align-items: stretch;
    }

    .revenue-value {
      text-align: right;
    }
  }
</style>
