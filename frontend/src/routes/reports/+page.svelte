<script>
  import { onMount } from 'svelte';
  import { analyticsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import ReportSummaryGrid from '$lib/components/reports/ReportSummaryGrid.svelte';
  import RevenueBreakdownCard from '$lib/components/reports/RevenueBreakdownCard.svelte';
  import TopClientsCard from '$lib/components/reports/TopClientsCard.svelte';

  let loading = true;
  let revenueData = null;
  let clientData = [];
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
  {:else}
    <ReportSummaryGrid totals={revenueData?.totals} />
    <RevenueBreakdownCard {revenueData} {year} {groupBy} {changeYear} {changeGroupBy} />
    <TopClientsCard {clientData} />
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
    to {
      transform: rotate(360deg);
    }
  }
</style>
