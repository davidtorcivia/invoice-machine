<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { formatDate, formatCurrency } from '$lib/stores';
  import { getEffectiveStatus, isOverdue } from '$lib/invoices/list';

  export let invoices = [];
  export let selectedIds = new Set();
  export let allSelected = false;
  export let sortBy = 'issue_date';
  export let sortDir = 'desc';
  export let statusConfig = {};

  const dispatch = createEventDispatcher();
</script>

<div class="table-container table-view">
  <table class="table">
    <thead>
      <tr>
        <th class="checkbox-col">
          <input type="checkbox" checked={allSelected} on:change={() => dispatch('toggleselectall')} aria-label="Select all invoices" />
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'invoice_number'} on:click={() => dispatch('sort', 'invoice_number')}>
            Invoice
            {#if sortBy === 'invoice_number'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'client'} on:click={() => dispatch('sort', 'client')}>
            Client
            {#if sortBy === 'client'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>Line Items</th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'issue_date'} on:click={() => dispatch('sort', 'issue_date')}>
            Date
            {#if sortBy === 'issue_date'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'due_date'} on:click={() => dispatch('sort', 'due_date')}>
            Due Date
            {#if sortBy === 'due_date'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'status'} on:click={() => dispatch('sort', 'status')}>
            Status
            {#if sortBy === 'status'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th class="text-right">
          <button class="sortable-header justify-end" class:active={sortBy === 'total'} on:click={() => dispatch('sort', 'total')}>
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
        <tr
          on:click={() => dispatch('navigate', invoice.id)}
          class="clickable-row"
          class:row-overdue={overdue}
          class:row-selected={selectedIds.has(invoice.id)}
        >
          <td class="checkbox-col" on:click|stopPropagation>
            <input
              type="checkbox"
              checked={selectedIds.has(invoice.id)}
              on:change={() => dispatch('toggleselect', invoice.id)}
              aria-label="Select invoice {invoice.invoice_number}"
            />
          </td>
          <td>
            <a
              class="invoice-number font-mono row-link"
              href={`/invoices/${invoice.id}`}
              on:click|stopPropagation
            >#{invoice.invoice_number}</a>
          </td>
          <td><span class="client-name">{invoice.client_business || invoice.client_name || '---'}</span></td>
          <td>
            {#if invoice.line_items_count > 0}
              <div class="line-items-cell" title={invoice.line_items_preview}>
                <span class="line-items-text">{invoice.line_items_preview}</span>
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
          <td class="text-right"><span class="invoice-total">{formatCurrency(invoice.total, invoice.currency_code)}</span></td>
          <td class="actions-col">
            <div class="action-buttons">
              {#if invoice.document_type !== 'quote' && (invoice.status === 'sent' || invoice.status === 'overdue')}
                <button class="btn btn-ghost btn-icon btn-sm" on:click={(event) => { event.stopPropagation(); dispatch('markpaid', invoice.id); }} title="Mark as paid">
                  <Icon name="check" size="sm" />
                </button>
              {/if}
              <button class="btn btn-ghost btn-icon btn-sm" on:click={(event) => { event.stopPropagation(); dispatch('delete', invoice); }} title="Delete">
                <Icon name="trash" size="sm" />
              </button>
            </div>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .table-view {
    display: block;
  }

  .checkbox-col {
    width: 48px;
  }

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

  /* Keyboard-accessible link styled to match the rest of the row. */
  a.row-link {
    text-decoration: none;
    color: inherit;
  }

  a.row-link:hover,
  a.row-link:focus-visible {
    text-decoration: underline;
  }

  .client-name {
    font-weight: 500;
  }

  .invoice-total {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .line-items-cell {
    max-width: 360px;
  }

  .line-items-text {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
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

  @media (max-width: 768px) {
    .table-view {
      display: none;
    }
  }
</style>
