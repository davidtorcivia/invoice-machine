<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { invoicesApi, clientsApi } from '$lib/api';
  import { formatDate, formatCurrency, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

  let invoices = [];
  let clients = [];
  let loading = true;
  let filterStatus = '';
  let filterClient = '';
  let filterYear = '';
  let filterFromDate = '';
  let filterToDate = '';
  let sortBy = 'issue_date';
  let sortDir = 'desc';

  // Sort options for mobile dropdown
  const sortOptions = [
    { value: 'issue_date-desc', label: 'Date (newest)', field: 'issue_date', dir: 'desc' },
    { value: 'issue_date-asc', label: 'Date (oldest)', field: 'issue_date', dir: 'asc' },
    { value: 'due_date-desc', label: 'Due Date (newest)', field: 'due_date', dir: 'desc' },
    { value: 'due_date-asc', label: 'Due Date (oldest)', field: 'due_date', dir: 'asc' },
    { value: 'client-asc', label: 'Client (A-Z)', field: 'client', dir: 'asc' },
    { value: 'client-desc', label: 'Client (Z-A)', field: 'client', dir: 'desc' },
    { value: 'invoice_number-desc', label: 'Invoice # (newest)', field: 'invoice_number', dir: 'desc' },
    { value: 'invoice_number-asc', label: 'Invoice # (oldest)', field: 'invoice_number', dir: 'asc' },
    { value: 'total-desc', label: 'Total (high-low)', field: 'total', dir: 'desc' },
    { value: 'total-asc', label: 'Total (low-high)', field: 'total', dir: 'asc' },
    { value: 'status-asc', label: 'Status (A-Z)', field: 'status', dir: 'asc' },
  ];

  // Generate year options (current year down to 5 years ago)
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 6 }, (_, i) => currentYear - i);

  $: selectedSortOption = `${sortBy}-${sortDir}`;

  // Delete modal state
  let showDeleteModal = false;
  let deleteTargetId = null;
  let deleteTargetNumber = '';
  let deleting = false;

  const statusConfig = {
    draft: { class: 'badge-draft', label: 'Draft' },
    sent: { class: 'badge-sent', label: 'Sent' },
    paid: { class: 'badge-paid', label: 'Paid' },
    overdue: { class: 'badge-overdue', label: 'Overdue' },
    cancelled: { class: 'badge-cancelled', label: 'Cancelled' },
  };

  function isOverdue(invoice) {
    if (invoice.status === 'paid' || invoice.status === 'cancelled' || invoice.status === 'draft') {
      return false;
    }
    if (!invoice.due_date) return false;
    const dueDate = new Date(invoice.due_date);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return dueDate < today;
  }

  function getEffectiveStatus(invoice) {
    if (isOverdue(invoice) && invoice.status !== 'overdue') {
      return 'overdue';
    }
    return invoice.status;
  }

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const params = {
        sort_by: sortBy,
        sort_dir: sortDir,
      };
      if (filterStatus) params.status = filterStatus;
      if (filterClient) params.client_id = filterClient;

      // Handle date filtering - year takes precedence over manual date range
      if (filterYear) {
        params.from_date = `${filterYear}-01-01`;
        params.to_date = `${filterYear}-12-31`;
      } else {
        if (filterFromDate) params.from_date = filterFromDate;
        if (filterToDate) params.to_date = filterToDate;
      }

      [invoices, clients] = await Promise.all([
        invoicesApi.list(params),
        clientsApi.list(),
      ]);
    } catch (error) {
      toast.error('Failed to load invoices');
    } finally {
      loading = false;
    }
  }

  function handleSort(field) {
    if (sortBy === field) {
      // Toggle direction if same field
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      // New field, default to descending for dates/totals, ascending for text
      sortBy = field;
      sortDir = ['client', 'status'].includes(field) ? 'asc' : 'desc';
    }
    loadData();
  }

  function handleSortDropdown(e) {
    const option = sortOptions.find(o => o.value === e.target.value);
    if (option) {
      sortBy = option.field;
      sortDir = option.dir;
      loadData();
    }
  }

  function handleYearChange() {
    // Clear manual date range when year is selected
    if (filterYear) {
      filterFromDate = '';
      filterToDate = '';
    }
    loadData();
  }

  function handleDateChange() {
    // Clear year filter when manual dates are used
    if (filterFromDate || filterToDate) {
      filterYear = '';
    }
    loadData();
  }

  function clearAllFilters() {
    filterStatus = '';
    filterClient = '';
    filterYear = '';
    filterFromDate = '';
    filterToDate = '';
    sortBy = 'issue_date';
    sortDir = 'desc';
    loadData();
  }

  $: hasFilters = filterStatus || filterClient || filterYear || filterFromDate || filterToDate;

  function openDeleteModal(e, invoice) {
    e.stopPropagation();
    deleteTargetId = invoice.id;
    deleteTargetNumber = invoice.invoice_number;
    showDeleteModal = true;
  }

  async function confirmDelete() {
    if (!deleteTargetId) return;
    deleting = true;
    try {
      await invoicesApi.delete(deleteTargetId);
      toast.success('Invoice moved to trash');
      showDeleteModal = false;
      await loadData();
    } catch (error) {
      toast.error('Failed to delete invoice');
    } finally {
      deleting = false;
      deleteTargetId = null;
      deleteTargetNumber = '';
    }
  }

  function cancelDelete() {
    showDeleteModal = false;
    deleteTargetId = null;
    deleteTargetNumber = '';
  }

  async function markAsPaid(e, id) {
    e.stopPropagation();
    try {
      await invoicesApi.update(id, { status: 'paid' });
      toast.success('Invoice marked as paid');
      await loadData();
    } catch (error) {
      toast.error('Failed to update invoice');
    }
  }
</script>

<Header title="Invoices" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Invoices</h1>
      <p class="page-subtitle">{invoices.length} invoice{invoices.length !== 1 ? 's' : ''}</p>
    </div>
    <a href="/invoices/new" class="btn btn-primary">
      <Icon name="plus" size="sm" />
      New Invoice
    </a>
  </div>

  <!-- Filters -->
  <div class="filters-bar">
    <div class="filters-row">
      <div class="filter-group">
        <label for="status-filter" class="filter-label">Status</label>
        <select
          id="status-filter"
          class="select"
          bind:value={filterStatus}
          on:change={loadData}
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="sent">Sent</option>
          <option value="paid">Paid</option>
          <option value="overdue">Overdue</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div class="filter-group">
        <label for="client-filter" class="filter-label">Client</label>
        <select
          id="client-filter"
          class="select"
          bind:value={filterClient}
          on:change={loadData}
        >
          <option value="">All Clients</option>
          {#each clients as client}
            <option value={client.id}>{client.business_name || client.name}</option>
          {/each}
        </select>
      </div>

      <div class="filter-group">
        <label for="year-filter" class="filter-label">Year</label>
        <select
          id="year-filter"
          class="select"
          bind:value={filterYear}
          on:change={handleYearChange}
        >
          <option value="">All Years</option>
          {#each yearOptions as year}
            <option value={year}>{year}</option>
          {/each}
        </select>
      </div>

      <div class="filter-group date-range-group">
        <label class="filter-label">Date Range</label>
        <div class="date-range-inputs">
          <input
            type="date"
            class="input input-sm"
            bind:value={filterFromDate}
            on:change={handleDateChange}
            placeholder="From"
          />
          <span class="date-range-separator">to</span>
          <input
            type="date"
            class="input input-sm"
            bind:value={filterToDate}
            on:change={handleDateChange}
            placeholder="To"
          />
        </div>
      </div>

      <!-- Sort dropdown (visible on mobile) -->
      <div class="filter-group sort-dropdown-mobile">
        <label for="sort-select" class="filter-label">Sort</label>
        <select
          id="sort-select"
          class="select"
          value={selectedSortOption}
          on:change={handleSortDropdown}
        >
          {#each sortOptions as option}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </div>
    </div>

    {#if hasFilters}
      <button
        class="btn btn-ghost btn-sm clear-filters"
        on:click={clearAllFilters}
      >
        <Icon name="x" size="sm" />
        Clear filters
      </button>
    {/if}
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if invoices.length > 0}
    <!-- Table view (hidden on small screens) -->
    <div class="table-container table-view">
      <table class="table">
        <thead>
          <tr>
            <th>
              <button class="sortable-header" class:active={sortBy === 'invoice_number'} on:click={() => handleSort('invoice_number')}>
                Invoice
                {#if sortBy === 'invoice_number'}
                  <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
                {/if}
              </button>
            </th>
            <th>
              <button class="sortable-header" class:active={sortBy === 'client'} on:click={() => handleSort('client')}>
                Client
                {#if sortBy === 'client'}
                  <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
                {/if}
              </button>
            </th>
            <th>
              <button class="sortable-header" class:active={sortBy === 'issue_date'} on:click={() => handleSort('issue_date')}>
                Date
                {#if sortBy === 'issue_date'}
                  <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
                {/if}
              </button>
            </th>
            <th>
              <button class="sortable-header" class:active={sortBy === 'due_date'} on:click={() => handleSort('due_date')}>
                Due Date
                {#if sortBy === 'due_date'}
                  <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
                {/if}
              </button>
            </th>
            <th>
              <button class="sortable-header" class:active={sortBy === 'status'} on:click={() => handleSort('status')}>
                Status
                {#if sortBy === 'status'}
                  <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
                {/if}
              </button>
            </th>
            <th class="text-right">
              <button class="sortable-header justify-end" class:active={sortBy === 'total'} on:click={() => handleSort('total')}>
                Total
                {#if sortBy === 'total'}
                  <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
                {/if}
              </button>
            </th>
            <th class="actions-col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each invoices as invoice}
            {@const effectiveStatus = getEffectiveStatus(invoice)}
            {@const overdue = isOverdue(invoice)}
            <tr on:click={() => goto(`/invoices/${invoice.id}`)} class="clickable-row" class:row-overdue={overdue}>
              <td>
                <span class="invoice-number font-mono">#{invoice.invoice_number}</span>
              </td>
              <td>
                <span class="client-name">{invoice.client_business || invoice.client_name || '---'}</span>
              </td>
              <td class="text-secondary">{formatDate(invoice.issue_date)}</td>
              <td class:text-overdue={overdue} class:text-secondary={!overdue}>
                {invoice.due_date ? formatDate(invoice.due_date) : '---'}
                {#if overdue}
                  <span class="overdue-indicator">overdue</span>
                {/if}
              </td>
              <td>
                <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
                  {statusConfig[effectiveStatus]?.label || effectiveStatus}
                </span>
              </td>
              <td class="text-right">
                <span class="invoice-total">{formatCurrency(invoice.total)}</span>
              </td>
              <td class="actions-col">
                <div class="action-buttons">
                  {#if invoice.status === 'sent' || invoice.status === 'overdue'}
                    <button
                      class="btn btn-ghost btn-icon btn-sm"
                      on:click={(e) => markAsPaid(e, invoice.id)}
                      title="Mark as paid"
                    >
                      <Icon name="check" size="sm" />
                    </button>
                  {/if}
                  <button
                    class="btn btn-ghost btn-icon btn-sm"
                    on:click={(e) => openDeleteModal(e, invoice)}
                    title="Delete"
                  >
                    <Icon name="trash" size="sm" />
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Card view (shown on small screens) -->
    <div class="invoice-cards">
      {#each invoices as invoice}
        {@const effectiveStatus = getEffectiveStatus(invoice)}
        {@const overdue = isOverdue(invoice)}
        <div class="invoice-card" class:card-overdue={overdue}>
          <button class="invoice-card-main" on:click={() => goto(`/invoices/${invoice.id}`)}>
            <div class="invoice-card-header">
              <span class="invoice-card-number font-mono">#{invoice.invoice_number}</span>
              <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
                {statusConfig[effectiveStatus]?.label || effectiveStatus}
              </span>
            </div>
            <div class="invoice-card-client">{invoice.client_business || invoice.client_name || '---'}</div>
            <div class="invoice-card-footer">
              <span class="invoice-card-date" class:text-overdue={overdue}>
                {invoice.due_date ? formatDate(invoice.due_date) : formatDate(invoice.issue_date)}
                {#if overdue}
                  <span class="overdue-indicator">overdue</span>
                {/if}
              </span>
              <span class="invoice-card-total">{formatCurrency(invoice.total)}</span>
            </div>
          </button>
          <div class="invoice-card-actions">
            {#if invoice.status === 'sent' || invoice.status === 'overdue'}
              <button
                class="btn btn-ghost btn-icon"
                on:click={(e) => markAsPaid(e, invoice.id)}
                title="Mark as paid"
              >
                <Icon name="check" size="sm" />
              </button>
            {/if}
            <button
              class="btn btn-ghost btn-icon"
              on:click={(e) => openDeleteModal(e, invoice)}
              title="Delete"
            >
              <Icon name="trash" size="sm" />
            </button>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty-state">
      <div class="empty-state-icon">
        <Icon name="invoice" size="xl" />
      </div>
      <div class="empty-state-title">No invoices found</div>
      <div class="empty-state-description">
        {#if filterStatus || filterClient}
          Try adjusting your filters or create a new invoice.
        {:else}
          Create your first invoice to get started.
        {/if}
      </div>
      <button class="btn btn-primary mt-6" on:click={() => goto('/invoices/new')}>
        <Icon name="plus" size="sm" />
        Create Invoice
      </button>
    </div>
  {/if}
</div>

<ConfirmModal
  show={showDeleteModal}
  title="Delete Invoice"
  message="Move invoice #{deleteTargetNumber} to trash? You can restore it later from the Trash."
  confirmText="Delete"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deleting}
  onConfirm={confirmDelete}
  onCancel={cancelDelete}
/>

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

  .filters-bar {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin-bottom: var(--space-6);
    padding: var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .filters-row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-4);
  }

  .filter-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 140px;
  }

  .filter-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .date-range-group {
    min-width: auto;
  }

  .date-range-inputs {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .date-range-inputs .input {
    width: 140px;
  }

  .date-range-separator {
    color: var(--color-text-tertiary);
    font-size: 0.8125rem;
  }

  .sort-dropdown-mobile {
    display: none;
  }

  .clear-filters {
    align-self: flex-start;
    color: var(--color-text-secondary);
  }

  /* Sortable table headers */
  .sortable-header {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    font-weight: 600;
    color: var(--color-text-secondary);
    cursor: pointer;
    transition: color var(--transition-fast);
  }

  .sortable-header:hover {
    color: var(--color-text);
  }

  .sortable-header.active {
    color: var(--color-primary);
  }

  .sortable-header.justify-end {
    justify-content: flex-end;
    width: 100%;
  }

  .sortable-header :global(.icon) {
    flex-shrink: 0;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .clickable-row {
    cursor: pointer;
  }

  .row-overdue {
    background-color: rgba(239, 68, 68, 0.08);
  }

  .row-overdue:hover {
    background-color: rgba(239, 68, 68, 0.12);
  }

  .text-overdue {
    color: var(--color-danger, #dc2626);
    font-weight: 500;
  }

  .overdue-indicator {
    display: inline-block;
    margin-left: var(--space-2);
    padding: 0.125rem 0.375rem;
    font-size: 0.625rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.025em;
    color: var(--color-danger);
    background-color: var(--color-danger-light);
    border-radius: var(--radius-sm);
  }

  .invoice-number {
    font-weight: 600;
    color: var(--color-text);
  }

  .client-name {
    font-weight: 500;
  }

  .invoice-total {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .actions-col {
    width: 100px;
    text-align: right;
  }

  .action-buttons {
    display: flex;
    gap: var(--space-1);
    justify-content: flex-end;
  }

  /* Invoice cards (mobile view) */
  .invoice-cards {
    display: none;
    padding: var(--space-3);
    gap: var(--space-3);
  }

  .invoice-card {
    display: flex;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .invoice-card.card-overdue {
    border-color: var(--color-danger-light);
    background: color-mix(in srgb, var(--color-danger) 5%, var(--color-bg-elevated));
  }

  .invoice-card-main {
    flex: 1;
    display: block;
    padding: var(--space-4);
    background: none;
    border: none;
    text-align: left;
    cursor: pointer;
    min-width: 0;
  }

  .invoice-card-main:hover {
    background: var(--color-bg-hover);
  }

  .invoice-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-2);
    gap: var(--space-2);
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
    gap: var(--space-2);
  }

  .invoice-card-date {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
  }

  .invoice-card-total {
    font-weight: 600;
    color: var(--color-text);
    white-space: nowrap;
  }

  .invoice-card-actions {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: var(--space-2);
    border-left: 1px solid var(--color-border-light);
    background: var(--color-bg);
  }

  @media (max-width: 900px) {
    .date-range-group {
      order: 10;
      flex-basis: 100%;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .filters-bar {
      padding: var(--space-4);
    }

    .filters-row {
      gap: var(--space-3);
    }

    .filter-group {
      flex: 1 1 calc(50% - var(--space-3));
      min-width: 140px;
    }

    .date-range-group {
      flex-basis: 100%;
    }

    .date-range-inputs .input {
      flex: 1;
      width: auto;
      min-width: 0;
    }
  }

  @media (max-width: 640px) {
    .table th:nth-child(4),
    .table td:nth-child(4) {
      display: none;
    }
  }

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .filters-bar {
      padding: var(--space-3);
    }

    .filter-group {
      flex: 1 1 100%;
    }

    .sort-dropdown-mobile {
      display: flex;
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
</style>
