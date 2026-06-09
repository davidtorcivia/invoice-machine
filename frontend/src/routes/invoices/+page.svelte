<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { invoicesApi, clientsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import InvoiceBulkActionBar from '$lib/components/invoices/InvoiceBulkActionBar.svelte';
  import InvoiceCards from '$lib/components/invoices/InvoiceCards.svelte';
  import InvoiceFiltersBar from '$lib/components/invoices/InvoiceFiltersBar.svelte';
  import InvoicePagination from '$lib/components/invoices/InvoicePagination.svelte';
  import InvoiceTable from '$lib/components/invoices/InvoiceTable.svelte';
  import {
    getBulkActionLabel,
    getBulkActionMessage,
    sortOptions,
    statusConfig,
    yearOptions
  } from '$lib/invoices/list';

  let invoices = [];
  let clients = [];
  let loading = true;
  let filterStatus = '';
  let filterClient = '';
  let filterDocumentType = '';
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
    has_prev: false
  };

  let showDeleteModal = false;
  let deleteTargetId = null;
  let deleteTargetNumber = '';
  let deleting = false;

  let selectedIds = new Set();
  let showBulkModal = false;
  let bulkAction = null;
  let bulkActionLoading = false;

  $: selectedSortOption = `${sortBy}-${sortDir}`;
  $: pageStart = pagination.total === 0 ? 0 : ((pagination.page - 1) * pagination.per_page) + 1;
  $: pageEnd = pagination.total === 0 ? 0 : Math.min(pagination.total, pageStart + invoices.length - 1);
  $: allSelected = invoices.length > 0 && selectedIds.size === invoices.length;
  $: selectedInvoices = invoices.filter((invoice) => selectedIds.has(invoice.id));
  $: canMarkSent = selectedInvoices.some((invoice) => invoice.status === 'draft');
  $: canMarkPaid = selectedInvoices.some((invoice) => invoice.document_type !== 'quote' && ['sent', 'overdue'].includes(invoice.status));
  $: hasFilters = Boolean(filterStatus || filterClient || filterDocumentType || filterYear || filterFromDate || filterToDate);

  onMount(async () => {
    // Clients populate the filter dropdown and never change as you page/sort/filter
    // invoices, so fetch them once here instead of on every loadData().
    await Promise.all([loadClients(), loadData()]);
  });

  async function loadClients() {
    try {
      clients = await clientsApi.list();
    } catch (error) {
      // Non-fatal: the client filter just stays empty.
      console.error('Failed to load clients', error);
    }
  }

  async function loadData() {
    loading = true;
    clearSelection();
    try {
      const params = {
        sort_by: sortBy,
        sort_dir: sortDir,
        page: currentPage,
        per_page: perPage
      };
      if (filterStatus) params.status = filterStatus;
      if (filterClient) params.client_id = filterClient;
      if (filterDocumentType) params.document_type = filterDocumentType;

      if (filterYear) {
        params.from_date = `${filterYear}-01-01`;
        params.to_date = `${filterYear}-12-31`;
      } else {
        if (filterFromDate) params.from_date = filterFromDate;
        if (filterToDate) params.to_date = filterToDate;
      }

      const invoicesData = await invoicesApi.listPaginated(params);

      invoices = invoicesData.items || [];
      pagination = invoicesData.pagination || pagination;
      currentPage = pagination.page || currentPage;
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
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortBy = field;
      sortDir = ['client', 'status'].includes(field) ? 'asc' : 'desc';
    }
    loadFirstPage();
  }

  function handleSortDropdown(event) {
    const option = sortOptions.find((item) => item.value === event.detail);
    if (!option) return;
    sortBy = option.field;
    sortDir = option.dir;
    loadFirstPage();
  }

  function handleYearChange() {
    if (filterYear) {
      filterFromDate = '';
      filterToDate = '';
    }
    loadFirstPage();
  }

  function handleDateChange() {
    if (filterFromDate || filterToDate) {
      filterYear = '';
    }
    loadFirstPage();
  }

  function clearAllFilters() {
    filterStatus = '';
    filterClient = '';
    filterDocumentType = '';
    filterYear = '';
    filterFromDate = '';
    filterToDate = '';
    sortBy = 'issue_date';
    sortDir = 'desc';
    loadFirstPage();
  }

  function toggleSelect(id) {
    if (selectedIds.has(id)) {
      selectedIds.delete(id);
    } else {
      selectedIds.add(id);
    }
    selectedIds = selectedIds;
  }

  function toggleSelectAll() {
    selectedIds = allSelected ? new Set() : new Set(invoices.map((invoice) => invoice.id));
  }

  function clearSelection() {
    selectedIds = new Set();
  }

  function openBulkActionModal(action) {
    bulkAction = action;
    showBulkModal = true;
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

  function openDeleteModal(invoice) {
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

  async function markAsPaid(id) {
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

  <InvoiceFiltersBar
    {clients}
    {sortOptions}
    {yearOptions}
    {selectedSortOption}
    bind:filterStatus
    bind:filterClient
    bind:filterDocumentType
    bind:filterYear
    bind:filterFromDate
    bind:filterToDate
    {hasFilters}
    on:filterchange={loadFirstPage}
    on:yearchange={handleYearChange}
    on:datechange={handleDateChange}
    on:sortchange={handleSortDropdown}
    on:clear={clearAllFilters}
  />

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if invoices.length > 0}
    <InvoiceTable
      {invoices}
      {selectedIds}
      {allSelected}
      {sortBy}
      {sortDir}
      {statusConfig}
      on:navigate={(event) => goto(`/invoices/${event.detail}`)}
      on:toggleselect={(event) => toggleSelect(event.detail)}
      on:toggleselectall={toggleSelectAll}
      on:sort={(event) => handleSort(event.detail)}
      on:delete={(event) => openDeleteModal(event.detail)}
      on:markpaid={(event) => markAsPaid(event.detail)}
    />

    <InvoiceCards
      {invoices}
      {selectedIds}
      {statusConfig}
      on:navigate={(event) => goto(`/invoices/${event.detail}`)}
      on:toggleselect={(event) => toggleSelect(event.detail)}
      on:delete={(event) => openDeleteModal(event.detail)}
      on:markpaid={(event) => markAsPaid(event.detail)}
    />

    <InvoicePagination {pageStart} {pageEnd} {pagination} {loading} on:pagechange={(event) => changePage(event.detail)} />
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

<InvoiceBulkActionBar
  selectedCount={selectedIds.size}
  {canMarkSent}
  {canMarkPaid}
  on:clear={clearSelection}
  on:action={(event) => openBulkActionModal(event.detail)}
/>

<ConfirmModal
  show={showBulkModal}
  title={bulkAction === 'delete' ? 'Delete Invoices' : 'Confirm Bulk Action'}
  message={getBulkActionMessage(bulkAction, selectedInvoices, selectedIds.size)}
  confirmText={getBulkActionLabel(bulkAction)}
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

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }

  .empty-state {
    text-align: center;
    padding: var(--space-12);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
  }

  .empty-state-icon {
    color: var(--color-text-tertiary);
    margin-bottom: var(--space-4);
  }

  .empty-state-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: var(--space-2);
  }

  .empty-state-description {
    color: var(--color-text-secondary);
  }
</style>
