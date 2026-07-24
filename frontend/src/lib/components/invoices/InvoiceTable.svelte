<script lang="ts">
  import { createBubbler, stopPropagation } from 'svelte/legacy';

  const bubble = createBubbler();
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { formatDate, formatCurrency } from '$lib/stores';
  import { getEffectiveStatus, isOverdue } from '$lib/invoices/list';

  interface Props {
    invoices?: any;
    selectedIds?: any;
    allSelected?: boolean;
    sortBy?: string;
    sortDir?: string;
    statusConfig?: any;
  }

  let {
    invoices = [],
    selectedIds = new Set(),
    allSelected = false,
    sortBy = 'issue_date',
    sortDir = 'desc',
    statusConfig = {}
  }: Props = $props();

  const dispatch = createEventDispatcher();
</script>

<div class="table-container table-view">
  <table class="table">
    <thead>
      <tr>
        <th class="checkbox-col">
          <input type="checkbox" checked={allSelected} onchange={() => dispatch('toggleselectall')} aria-label="Select all invoices" />
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'invoice_number'} onclick={() => dispatch('sort', 'invoice_number')}>
            Invoice
            {#if sortBy === 'invoice_number'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'client'} onclick={() => dispatch('sort', 'client')}>
            Client
            {#if sortBy === 'client'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>Line Items</th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'issue_date'} onclick={() => dispatch('sort', 'issue_date')}>
            Date
            {#if sortBy === 'issue_date'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'due_date'} onclick={() => dispatch('sort', 'due_date')}>
            Due Date
            {#if sortBy === 'due_date'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th>
          <button class="sortable-header" class:active={sortBy === 'status'} onclick={() => dispatch('sort', 'status')}>
            Status
            {#if sortBy === 'status'}
              <Icon name={sortDir === 'asc' ? 'chevronUp' : 'chevronDown'} size="xs" />
            {/if}
          </button>
        </th>
        <th class="text-right">
          <button class="sortable-header justify-end" class:active={sortBy === 'total'} onclick={() => dispatch('sort', 'total')}>
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
          onclick={() => dispatch('navigate', invoice.id)}
          class="clickable-row"
          class:row-overdue={overdue}
          class:row-selected={selectedIds.has(invoice.id)}
        >
          <td class="checkbox-col" onclick={stopPropagation(bubble('click'))}>
            <input
              type="checkbox"
              checked={selectedIds.has(invoice.id)}
              onchange={() => dispatch('toggleselect', invoice.id)}
              aria-label="Select invoice {invoice.invoice_number}"
            />
          </td>
          <td>
            <a
              class="invoice-number font-mono row-link"
              href={`/invoices/${invoice.id}`}
              onclick={stopPropagation(bubble('click'))}
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
                <button class="btn btn-ghost btn-icon btn-sm" onclick={(event) => { event.stopPropagation(); dispatch('markpaid', invoice.id); }} title="Mark as paid">
                  <Icon name="check" size="sm" />
                </button>
              {/if}
              <button class="btn btn-ghost btn-icon btn-sm" onclick={(event) => { event.stopPropagation(); dispatch('delete', invoice); }} title="Delete">
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
