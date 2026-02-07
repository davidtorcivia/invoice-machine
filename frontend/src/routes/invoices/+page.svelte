<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { fly } from 'svelte/transition';
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
  let currentPage = 1;
  let perPage = 25;
  let pagination = {
    page: 1,
    per_page: 25,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_prev: false,
  };

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
  $: pageStart = pagination.total === 0 ? 0 : ((pagination.page - 1) * pagination.per_page) + 1;
  $: pageEnd = pagination.total === 0 ? 0 : Math.min(pagination.total, pageStart + invoices.length - 1);

  // Delete modal state
  let showDeleteModal = false;
  let deleteTargetId = null;
  let deleteTargetNumber = '';
  let deleting = false;

  // Selection state for bulk actions
  let selectedIds = new Set();

  // Reactive: check if all visible invoices are selected
  $: allSelected = invoices.length > 0 && selectedIds.size === invoices.length;

  // Get selected invoices for action validation
  $: selectedInvoices = invoices.filter(inv => selectedIds.has(inv.id));

  // Determine which bulk actions are available
  $: canMarkSent = selectedInvoices.some(inv => inv.status === 'draft');
  $: canMarkPaid = selectedInvoices.some(inv => ['sent', 'overdue'].includes(inv.status));

  // Bulk action modal state
  let showBulkModal = false;
  let bulkAction = null;
  let bulkActionLoading = false;

  function toggleSelect(id) {
    if (selectedIds.has(id)) {
      selectedIds.delete(id);
    } else {
      selectedIds.add(id);
    }
    selectedIds = selectedIds; // Trigger reactivity
  }

  function toggleSelectAll() {
    if (allSelected) {
      selectedIds = new Set();
    } else {
      selectedIds = new Set(invoices.map(inv => inv.id));
    }
  }

  function clearSelection() {
    selectedIds = new Set();
  }

  function openBulkActionModal(action) {
    bulkAction = action;
    showBulkModal = true;
  }

  function getActionLabel(action) {
    const labels = {
      mark_sent: 'Mark as Sent',
      mark_paid: 'Mark as Paid',
      delete: 'Delete',
    };
    return labels[action] || action;
  }

  function getBulkActionMessage() {
    const count = selectedIds.size;
    switch (bulkAction) {
      case 'mark_sent': {
        const draftCount = selectedInvoices.filter(inv => inv.status === 'draft').length;
        const skipped = count - draftCount;
        return `Mark ${draftCount} draft invoice${draftCount !== 1 ? 's' : ''} as sent?${skipped > 0 ? ` (${skipped} non-draft will be skipped)` : ''}`;
      }
      case 'mark_paid': {
        const eligibleCount = selectedInvoices.filter(inv => ['sent', 'overdue'].includes(inv.status)).length;
        const skipped = count - eligibleCount;
        return `Mark ${eligibleCount} invoice${eligibleCount !== 1 ? 's' : ''} as paid?${skipped > 0 ? ` (${skipped} ineligible will be skipped)` : ''}`;
      }
      case 'delete':
        return `Move ${count} invoice${count !== 1 ? 's' : ''} to trash? You can restore them later.`;
      default:
        return `Apply action to ${count} invoice${count !== 1 ? 's' : ''}?`;
    }
  }

  async function executeBulkAction() {
    if (!bulkAction || selectedIds.size === 0) return;

    bulkActionLoading = true;
    try {
      const result = await invoicesApi.bulkAction(bulkAction, Array.from(selectedIds));

      if (result.failed === 0) {
        const pastTense = { mark_sent: 'marked as sent', mark_paid: 'marked as paid', delete: 'deleted' };
        toast.success(`Successfully ${pastTense[bulkAction] || 'updated'} ${result.successful} invoice${result.successful !== 1 ? 's' : ''}`);
      } else if (result.successful > 0) {
        toast.info(`${result.successful} updated, ${result.failed} failed`);
      } else {
        toast.error('Failed to update invoices');
      }

      showBulkModal = false;
      clearSelection();
      await loadData();
    } catch (error) {
      toast.error(error.message || 'Bulk action failed');
    } finally {
      bulkActionLoading = false;
    }
  }

  function cancelBulkAction() {
    showBulkModal = false;
    bulkAction = null;
  }

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
    clearSelection(); // Clear selection when filters/sort change
    try {
      const params = {
        sort_by: sortBy,
        sort_dir: sortDir,
        page: currentPage,
        per_page: perPage,
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

      const [invoicesData, clientsData] = await Promise.all([
        invoicesApi.listPaginated(params),
        clientsApi.list(),
      ]);

      invoices = invoicesData.items || [];
      pagination = invoicesData.pagination || pagination;
      currentPage = pagination.page || currentPage;
      clients = clientsData;
    } catch (error) {
      toast.error('Failed to load invoices');
    } finally {
      loading = false;
    }
  }

  function loadFirstPage() {
    currentPage = 1;
    loadData();
  }

  function changePage(nextPage) {
    if (nextPage < 1 || nextPage > pagination.total_pages || nextPage === currentPage) return;
    currentPage = nextPage;
    loadData();
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
    loadFirstPage();
  }

  function handleSortDropdown(e) {
    const option = sortOptions.find(o => o.value === e.target.value);
    if (option) {
      sortBy = option.field;
      sortDir = option.dir;
      loadFirstPage();
    }
  }

  function handleYearChange() {
    // Clear manual date range when year is selected
    if (filterYear) {
      filterFromDate = '';
      filterToDate = '';
    }
    loadFirstPage();
  }

  function handleDateChange() {
    // Clear year filter when manual dates are used
    if (filterFromDate || filterToDate) {
      filterYear = '';
    }
    loadFirstPage();
  }

  function clearAllFilters() {
    filterStatus = '';
    filterClient = '';
    filterYear = '';
    filterFromDate = '';
    filterToDate = '';
    sortBy = 'issue_date';
    sortDir = 'desc';
    loadFirstPage();
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
      <p class="page-subtitle">
        {pagination.total} invoice{pagination.total !== 1 ? 's' : ''}
        {#if pagination.total_pages > 1}
          - Page {pagination.page} of {pagination.total_pages}
        {/if}
      </p>
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
          on:change={loadFirstPage}
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
          on:change={loadFirstPage}
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
            <th class="checkbox-col">
              <input
                type="checkbox"
                checked={allSelected}
                on:change={toggleSelectAll}
                aria-label="Select all invoices"
              />
            </th>
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
            <th>Line Items</th>
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
            <tr on:click={() => goto(`/invoices/${invoice.id}`)} class="clickable-row" class:row-overdue={overdue} class:row-selected={selectedIds.has(invoice.id)}>
              <td class="checkbox-col" on:click|stopPropagation>
                <input
                  type="checkbox"
                  checked={selectedIds.has(invoice.id)}
                  on:change={() => toggleSelect(invoice.id)}
                  aria-label="Select invoice {invoice.invoice_number}"
                />
              </td>
              <td>
                <span class="invoice-number font-mono">#{invoice.invoice_number}</span>
              </td>
              <td>
                <span class="client-name">{invoice.client_business || invoice.client_name || '---'}</span>
              </td>
              <td>
                {#if invoice.line_items_count > 0}
                  <div class="line-items-cell" title={invoice.line_items_preview}>
                    <span class="line-items-text">{invoice.line_items_preview}</span>
                    <span class="line-items-count">{invoice.line_items_count}</span>
                  </div>
                {:else}
                  <span class="text-secondary">---</span>
                {/if}
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
        <div class="invoice-card" class:card-overdue={overdue} class:card-selected={selectedIds.has(invoice.id)}>
          <div class="card-checkbox" on:click|stopPropagation>
            <input
              type="checkbox"
              checked={selectedIds.has(invoice.id)}
              on:change={() => toggleSelect(invoice.id)}
              aria-label="Select invoice {invoice.invoice_number}"
            />
          </div>
          <button class="invoice-card-main" on:click={() => goto(`/invoices/${invoice.id}`)}>
            <div class="invoice-card-header">
              <span class="invoice-card-number font-mono">#{invoice.invoice_number}</span>
              <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
                {statusConfig[effectiveStatus]?.label || effectiveStatus}
              </span>
            </div>
            <div class="invoice-card-client">{invoice.client_business || invoice.client_name || '---'}</div>
            {#if invoice.line_items_count > 0}
              <div class="invoice-card-items" title={invoice.line_items_preview}>
                {invoice.line_items_preview}
              </div>
            {/if}
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

    <div class="pagination-bar">
      <div class="pagination-summary">
        Showing {pageStart}-{pageEnd} of {pagination.total}
      </div>
      <div class="pagination-controls">
        <button
          class="btn btn-secondary btn-sm"
          on:click={() => changePage(currentPage - 1)}
          disabled={!pagination.has_prev || loading}
        >
          Previous
        </button>
        <span class="pagination-page">
          Page {pagination.page} of {Math.max(1, pagination.total_pages)}
        </span>
        <button
          class="btn btn-secondary btn-sm"
          on:click={() => changePage(currentPage + 1)}
          disabled={!pagination.has_next || loading}
        >
          Next
        </button>
      </div>
    </div>
  {:else}
    <div class="empty-state">
      <div class="empty-state-icon">
        <Icon name="invoice" size="xl" />
      </div>
      <div class="empty-state-title">No invoices found</div>
      <div class="empty-state-description">
        {#if hasFilters}
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

<!-- Floating bulk action bar -->
{#if selectedIds.size > 0}
  <div class="bulk-action-bar" transition:fly={{ y: 50, duration: 200 }}>
    <div class="bulk-action-info">
      <span class="selection-count">{selectedIds.size} selected</span>
      <button class="btn btn-ghost btn-sm" on:click={clearSelection}>
        Clear
      </button>
    </div>
    <div class="bulk-action-buttons">
      {#if canMarkSent}
        <button
          class="btn btn-secondary btn-sm"
          on:click={() => openBulkActionModal('mark_sent')}
          title="Mark selected draft invoices as sent"
        >
          <Icon name="send" size="sm" />
          <span class="btn-label">Mark Sent</span>
        </button>
      {/if}
      {#if canMarkPaid}
        <button
          class="btn btn-secondary btn-sm"
          on:click={() => openBulkActionModal('mark_paid')}
          title="Mark selected sent/overdue invoices as paid"
        >
          <Icon name="check" size="sm" />
          <span class="btn-label">Mark Paid</span>
        </button>
      {/if}
      <button
        class="btn btn-danger btn-sm"
        on:click={() => openBulkActionModal('delete')}
        title="Delete selected invoices"
      >
        <Icon name="trash" size="sm" />
        <span class="btn-label">Delete</span>
      </button>
    </div>
  </div>
{/if}

<!-- Bulk action confirmation modal -->
<ConfirmModal
  show={showBulkModal}
  title={bulkAction === 'delete' ? 'Delete Invoices' : 'Confirm Bulk Action'}
  message={getBulkActionMessage()}
  confirmText={getActionLabel(bulkAction)}
  cancelText="Cancel"
  variant={bulkAction === 'delete' ? 'danger' : 'primary'}
  icon={bulkAction === 'delete' ? 'trash' : 'check'}
  loading={bulkActionLoading}
  onConfirm={executeBulkAction}
  onCancel={cancelBulkAction}
/>

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
    width: 155px;
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

  .line-items-cell {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    max-width: 360px;
  }

  .line-items-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
  }

  .line-items-count {
    flex-shrink: 0;
    font-size: 0.6875rem;
    color: var(--color-text-tertiary);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    padding: 0.125rem 0.375rem;
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

  .invoice-card-items {
    margin-bottom: var(--space-2);
    color: var(--color-text-tertiary);
    font-size: 0.75rem;
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

  /* Checkbox column */
  .checkbox-col {
    width: 40px;
    text-align: center;
  }

  .checkbox-col input[type="checkbox"] {
    width: 16px;
    height: 16px;
    cursor: pointer;
    accent-color: var(--color-primary);
  }

  /* Selected row highlight */
  .row-selected {
    background-color: color-mix(in srgb, var(--color-primary) 10%, transparent);
  }

  .row-selected:hover {
    background-color: color-mix(in srgb, var(--color-primary) 15%, transparent);
  }

  /* Card selection */
  .invoice-card.card-selected {
    border-color: var(--color-primary);
    background: color-mix(in srgb, var(--color-primary) 5%, var(--color-bg-elevated));
  }

  .card-checkbox {
    position: absolute;
    top: var(--space-3);
    left: var(--space-3);
    z-index: 1;
  }

  .invoice-card {
    position: relative;
  }

  /* Floating bulk action bar */
  .bulk-action-bar {
    position: fixed;
    bottom: var(--space-6);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    z-index: 40;
  }

  .bulk-action-info {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .selection-count {
    font-weight: 600;
    color: var(--color-text);
    white-space: nowrap;
  }

  .bulk-action-buttons {
    display: flex;
    gap: var(--space-2);
  }

  .bulk-action-buttons .btn {
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }

  .pagination-bar {
    margin-top: var(--space-4);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .pagination-summary {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .pagination-controls {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .pagination-page {
    font-size: 0.8125rem;
    color: var(--color-text);
    min-width: 110px;
    text-align: center;
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

    .pagination-bar {
      flex-direction: column;
      align-items: stretch;
    }

    .pagination-controls {
      justify-content: space-between;
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

    /* Card checkbox adjustments for mobile */
    .invoice-card-main {
      padding-left: var(--space-10);
    }

    /* Floating action bar responsive */
    .bulk-action-bar {
      left: var(--space-3);
      right: var(--space-3);
      transform: none;
      flex-direction: column;
      gap: var(--space-3);
      padding: var(--space-3);
    }

    .bulk-action-buttons {
      width: 100%;
      justify-content: stretch;
    }

    .bulk-action-buttons .btn {
      flex: 1;
      justify-content: center;
    }

    .btn-label {
      display: none;
    }
  }

  /* Adjust sidebar offset for bulk action bar */
  @media (min-width: 769px) {
    .bulk-action-bar {
      margin-left: calc(var(--sidebar-width, 240px) / 2);
    }
  }
</style>
