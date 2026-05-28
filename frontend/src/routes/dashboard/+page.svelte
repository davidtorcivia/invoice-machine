<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { analyticsApi, invoicesApi, clientsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import DashboardStatsGrid from '$lib/components/dashboard/DashboardStatsGrid.svelte';
  import RecentInvoicesPanel from '$lib/components/dashboard/RecentInvoicesPanel.svelte';

  let stats = {
    totalOutstanding: 0,
    paidThisMonth: 0,
    draftCount: 0,
    clientCount: 0,
    currency: 'USD'
  };

  let recentInvoices = [];
  let loading = true;
  let loadError = false;

  async function load() {
    loading = true;
    loadError = false;
    try {
      const [dashboardData, invoicesData, clientsData] = await Promise.all([
        analyticsApi.getDashboardSummary(),
        invoicesApi.list({ document_type: 'invoice', limit: 10 }),
        clientsApi.list()
      ]);

      stats = {
        totalOutstanding: parseFloat(dashboardData.total_outstanding) || 0,
        paidThisMonth: parseFloat(dashboardData.paid_this_month) || 0,
        draftCount: dashboardData.draft_count || 0,
        clientCount: clientsData.length,
        currency: dashboardData.currency || 'USD'
      };
      recentInvoices = invoicesData;
    } catch (error) {
      loadError = true;
      toast.error('Failed to load dashboard');
    } finally {
      loading = false;
    }
  }

  onMount(load);
</script>

<Header title="Dashboard" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Dashboard</h1>
      <p class="page-subtitle">Overview of your invoicing activity</p>
    </div>
    <a href="/invoices/new" class="btn btn-primary">
      <Icon name="plus" size="sm" />
      New Invoice
    </a>
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if loadError}
    <div class="load-error">
      <p>Couldn't load the dashboard.</p>
      <button type="button" class="btn btn-secondary" on:click={load}>
        <Icon name="refresh" size="sm" />
        Retry
      </button>
    </div>
  {:else}
    <DashboardStatsGrid {stats} />
    <RecentInvoicesPanel {recentInvoices} on:open={(event) => goto(`/invoices/${event.detail}`)} on:new={() => goto('/invoices/new')} />
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
    padding: var(--space-12);
  }

  .load-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-12);
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
    to { transform: rotate(360deg); }
  }
</style>
