<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { invoicesApi, clientsApi } from '$lib/api';
  import { formatCurrency, formatDate, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let stats = {
    totalOutstanding: 0,
    paidThisMonth: 0,
    draftCount: 0,
    clientCount: 0,
  };

  let recentInvoices = [];
  let loading = true;

  onMount(async () => {
    try {
      const [invoicesData, clientsData] = await Promise.all([
        invoicesApi.list({ limit: 100 }),
        clientsApi.list(),
      ]);

      const now = new Date();
      const thisMonth = now.getMonth();
      const thisYear = now.getFullYear();

      stats.clientCount = clientsData.length;
      recentInvoices = invoicesData.slice(0, 5);

      for (const invoice of invoicesData) {
        const total = parseFloat(invoice.total);
        const invoiceDate = new Date(invoice.created_at);

        if (invoice.status === 'draft') {
          stats.draftCount++;
        } else if (invoice.status === 'sent' || invoice.status === 'overdue') {
          stats.totalOutstanding += total;
        }

        if (invoice.status === 'paid' && invoiceDate.getMonth() === thisMonth && invoiceDate.getFullYear() === thisYear) {
          stats.paidThisMonth += total;
        }
      }
    } catch (error) {
      toast.error('Failed to load dashboard');
    } finally {
      loading = false;
    }
  });

  const statusConfig = {
    draft: { class: 'badge-draft' },
    sent: { class: 'badge-sent' },
    paid: { class: 'badge-paid' },
    overdue: { class: 'badge-overdue' },
    cancelled: { class: 'badge-cancelled' },
  };
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
  {:else}
    <!-- Stats Grid -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon stat-outstanding">
          <Icon name="dollar" size="lg" />
        </div>
        <div class="stat-info">
          <div class="stat-value">{formatCurrency(stats.totalOutstanding)}</div>
          <div class="stat-label">Outstanding</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon stat-paid">
          <Icon name="check" size="lg" />
        </div>
        <div class="stat-info">
          <div class="stat-value">{formatCurrency(stats.paidThisMonth)}</div>
          <div class="stat-label">Paid This Month</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon stat-draft">
          <Icon name="pencil" size="lg" />
        </div>
        <div class="stat-info">
          <div class="stat-value">{stats.draftCount}</div>
          <div class="stat-label">Draft Invoices</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon stat-clients">
          <Icon name="users" size="lg" />
        </div>
        <div class="stat-info">
          <div class="stat-value">{stats.clientCount}</div>
          <div class="stat-label">Total Clients</div>
        </div>
      </div>
    </div>

    <!-- Recent Invoices -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">Recent Invoices</h2>
        <a href="/invoices" class="section-link">
          View all
          <Icon name="arrowRight" size="sm" />
        </a>
      </div>

      {#if recentInvoices.length > 0}
        <!-- Table view (hidden on small screens) -->
        <div class="table-container table-view">
          <table class="table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Client</th>
                <th>Date</th>
                <th>Status</th>
                <th class="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {#each recentInvoices as invoice}
                <tr on:click={() => goto(`/invoices/${invoice.id}`)} style="cursor: pointer;">
                  <td>
                    <span class="font-mono font-medium">#{invoice.invoice_number}</span>
                  </td>
                  <td class="text-secondary">{invoice.client_business || invoice.client_name || '---'}</td>
                  <td class="text-secondary">{formatDate(invoice.issue_date)}</td>
                  <td>
                    <span class="badge {statusConfig[invoice.status]?.class || 'badge-draft'}">
                      {invoice.status}
                    </span>
                  </td>
                  <td class="text-right font-medium">{formatCurrency(invoice.total)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

        <!-- Card view (shown on small screens) -->
        <div class="invoice-cards">
          {#each recentInvoices as invoice}
            <button class="invoice-card" on:click={() => goto(`/invoices/${invoice.id}`)}>
              <div class="invoice-card-header">
                <span class="invoice-card-number font-mono">#{invoice.invoice_number}</span>
                <span class="badge {statusConfig[invoice.status]?.class || 'badge-draft'}">
                  {invoice.status}
                </span>
              </div>
              <div class="invoice-card-client">{invoice.client_business || invoice.client_name || '---'}</div>
              <div class="invoice-card-footer">
                <span class="invoice-card-date">{formatDate(invoice.issue_date)}</span>
                <span class="invoice-card-total">{formatCurrency(invoice.total)}</span>
              </div>
            </button>
          {/each}
        </div>
      {:else}
        <div class="empty-state">
          <div class="empty-state-icon">
            <Icon name="invoice" size="xl" />
          </div>
          <div class="empty-state-title">No invoices yet</div>
          <div class="empty-state-description">
            Create your first invoice to get started tracking your income.
          </div>
          <button class="btn btn-primary mt-6" on:click={() => goto('/invoices/new')}>
            <Icon name="plus" size="sm" />
            Create Invoice
          </button>
        </div>
      {/if}
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

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  /* Stats Grid */
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

  /* Section */
  .section {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    overflow: hidden;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--color-border-light);
  }

  .section-title {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
  }

  .section-link {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-primary);
    text-decoration: none;
  }

  .section-link:hover {
    color: var(--color-primary-hover);
  }

  .section .table-container {
    border: none;
    border-radius: 0;
  }

  /* Invoice cards (mobile view) */
  .invoice-cards {
    display: none;
    padding: var(--space-3);
    gap: var(--space-3);
  }

  .invoice-card {
    display: block;
    width: 100%;
    padding: var(--space-4);
    background: var(--color-bg);
    border: 1px solid var(--color-border-light);
    border-radius: var(--radius-lg);
    text-align: left;
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .invoice-card:hover {
    border-color: var(--color-border);
    background: var(--color-bg-hover);
  }

  .invoice-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-2);
  }

  .invoice-card-number {
    font-weight: 600;
    color: var(--color-text);
  }

  .invoice-card-client {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    margin-bottom: var(--space-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .invoice-card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .invoice-card-date {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
  }

  .invoice-card-total {
    font-weight: 600;
    color: var(--color-text);
  }

  /* Large screens - better use of space */
  @media (min-width: 1400px) {
    .stats-grid {
      gap: var(--space-8);
    }

    .stat-card {
      padding: var(--space-8);
    }

    .stat-icon {
      width: 64px;
      height: 64px;
    }

    .stat-value {
      font-size: 2rem;
    }
  }

  @media (max-width: 1200px) {
    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
      gap: var(--space-4);
    }

    .stat-card {
      padding: var(--space-4);
    }

    .stat-value {
      font-size: 1.25rem;
    }

    .stat-icon {
      width: 44px;
      height: 44px;
    }
  }

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .stats-grid {
      grid-template-columns: 1fr;
      gap: var(--space-3);
    }

    .stat-card {
      padding: var(--space-3);
      flex-direction: row;
      gap: var(--space-3);
    }

    .stat-icon {
      width: 40px;
      height: 40px;
    }

    .stat-value {
      font-size: 1.125rem;
    }

    .stat-label {
      font-size: 0.8125rem;
    }

    .section-header {
      padding: var(--space-4);
    }

    .section-title {
      font-size: 1rem;
    }

    /* Switch to card view on small screens */
    .table-view {
      display: none;
    }

    .invoice-cards {
      display: flex;
      flex-direction: column;
    }
  }

  @media (max-width: 640px) {
    .table th:nth-child(3),
    .table td:nth-child(3) {
      display: none;
    }
  }

  @media (max-width: 480px) {
    .table th:nth-child(2),
    .table td:nth-child(2) {
      display: none;
    }
  }
</style>
