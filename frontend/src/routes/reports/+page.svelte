<script>
  import { onMount } from 'svelte';
  import { analyticsApi, exportApi, paymentsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import AgingReportCard from '$lib/components/reports/AgingReportCard.svelte';
  import ConsolidatedCard from '$lib/components/reports/ConsolidatedCard.svelte';
  import ReportSummaryGrid from '$lib/components/reports/ReportSummaryGrid.svelte';
  import RevenueBreakdownCard from '$lib/components/reports/RevenueBreakdownCard.svelte';
  import TopClientsCard from '$lib/components/reports/TopClientsCard.svelte';

  const EXPORT_KINDS = [
    { kind: 'invoices', label: 'Invoices' },
    { kind: 'line_items', label: 'Line items' },
    { kind: 'payments', label: 'Payments' },
    { kind: 'clients', label: 'Clients' }
  ];

  let loading = $state(true);
  let loadError = $state(false);
  let revenueData = $state(/** @type {any} */ (null));
  let clientData = $state([]);
  let agingData = $state(/** @type {any} */ (null));
  let consolidatedData = $state(/** @type {any} */ (null));
  let groupBy = $state('month');
  let year = $state(new Date().getFullYear());

  let fromDate = $derived(`${year}-01-01`);
  let toDate = $derived(`${year}-12-31`);

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    loadError = false;
    try {
      const [revenue, clients, aging, consolidated] = await Promise.all([
        analyticsApi.getRevenue({ from_date: fromDate, to_date: toDate, group_by: groupBy }),
        analyticsApi.getClientLifetimeValues({ limit: 10 }),
        paymentsApi.aging(),
        analyticsApi.getConsolidated({ from_date: fromDate, to_date: toDate })
      ]);
      revenueData = revenue;
      clientData = clients;
      agingData = aging;
      // Only worth showing once more than one currency is actually in play.
      consolidatedData =
        (consolidated?.coverage?.total_invoices || 0) > 0 &&
        (Object.keys(revenue?.by_currency || {}).length > 1 ||
          !consolidated?.coverage?.complete)
          ? consolidated
          : null;
    } catch (error) {
      loadError = true;
      toast.error('Failed to load analytics');
      console.error(error);
    } finally {
      loading = false;
    }
  }

  function exportUrl(kind) {
    return exportApi.url(kind, { from_date: fromDate, to_date: toDate });
  }

  async function changeYear(delta) {
    year += delta;
    await loadData();
  }

  async function changeGroupBy(nextGroupBy) {
    groupBy = nextGroupBy;
    await loadData();
  }
</script>

<Header title="Reports" subtitle="Revenue analytics and client insights" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Reports</h1>
      <p class="page-subtitle">Revenue analytics and client insights</p>
    </div>
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if loadError}
    <div class="load-error">
      <p>Couldn't load analytics.</p>
      <button type="button" class="btn btn-secondary" onclick={loadData}>
        <Icon name="refresh" size="sm" />
        Retry
      </button>
    </div>
  {:else}
    <ReportSummaryGrid totals={revenueData?.totals} />
    <RevenueBreakdownCard {revenueData} {year} {groupBy} {changeYear} {changeGroupBy} />
    <ConsolidatedCard consolidated={consolidatedData} />
    <AgingReportCard aging={agingData} />
    <TopClientsCard {clientData} />

    <div class="card">
      <div class="card-header">
        <div>
          <h2 class="card-title">Export</h2>
          <p class="card-subtitle">
            Download {year} records as CSV for your spreadsheet or accountant
          </p>
        </div>
      </div>
      <div class="card-body">
        <div class="export-actions">
          {#each EXPORT_KINDS as option (option.kind)}
            <a class="btn btn-secondary btn-sm" href={exportUrl(option.kind)} download>
              <Icon name="download" size="sm" />
              {option.label}
            </a>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 1400px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-6);
    gap: var(--space-4);
  }

  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .page-subtitle {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    margin: var(--space-1) 0 0 0;
  }

  .card-subtitle {
    margin: var(--space-1) 0 0;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .export-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-10);
  }

  .load-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-10);
    color: var(--color-text-secondary);
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
    to {
      transform: rotate(360deg);
    }
  }
</style>
