<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { formatDate, formatCurrency } from '$lib/stores';
  import { getEffectiveStatus, isOverdue } from '$lib/invoices/list';

  export let invoices = [];
  export let selectedIds = new Set();
  export let statusConfig = {};

  const dispatch = createEventDispatcher();
</script>

<div class="invoice-cards">
  {#each invoices as invoice}
    {@const effectiveStatus = getEffectiveStatus(invoice)}
    {@const overdue = isOverdue(invoice)}
    <div class="invoice-card" class:card-overdue={overdue} class:card-selected={selectedIds.has(invoice.id)}>
      <div class="card-checkbox">
        <input
          type="checkbox"
          checked={selectedIds.has(invoice.id)}
          on:click|stopPropagation
          on:change={() => dispatch('toggleselect', invoice.id)}
          aria-label="Select invoice {invoice.invoice_number}"
        />
      </div>
      <button class="invoice-card-main" on:click={() => dispatch('navigate', invoice.id)}>
        <div class="invoice-card-header">
          <span class="invoice-card-number font-mono">#{invoice.invoice_number}</span>
          <span class="badge {statusConfig[effectiveStatus]?.class || 'badge-draft'}">
            {statusConfig[effectiveStatus]?.label || effectiveStatus}
          </span>
        </div>
        <div class="invoice-card-client">{invoice.client_business || invoice.client_name || '---'}</div>
        {#if invoice.line_items_count > 0}
          <div class="invoice-card-items" title={invoice.line_items_preview}>{invoice.line_items_preview}</div>
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
          <button class="btn btn-ghost btn-icon" on:click={() => dispatch('markpaid', invoice.id)} title="Mark as paid">
            <Icon name="check" size="sm" />
          </button>
        {/if}
        <button class="btn btn-ghost btn-icon" on:click={() => dispatch('delete', invoice)} title="Delete">
          <Icon name="trash" size="sm" />
        </button>
      </div>
    </div>
  {/each}
</div>

<style>
  .invoice-cards {
    display: none;
    padding: var(--space-3);
    gap: var(--space-3);
  }

  .invoice-card {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: var(--space-3);
    align-items: flex-start;
    padding: var(--space-4);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .card-overdue {
    border-color: color-mix(in srgb, var(--color-danger) 35%, var(--color-border));
    background: color-mix(in srgb, var(--color-danger-light) 30%, var(--color-bg-elevated));
  }

  .card-selected {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-primary) 20%, transparent);
  }

  .invoice-card-main {
    border: 0;
    background: none;
    padding: 0;
    text-align: left;
    min-width: 0;
  }

  .invoice-card-header,
  .invoice-card-footer {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    align-items: center;
  }

  .invoice-card-header {
    margin-bottom: var(--space-2);
  }

  .invoice-card-number,
  .invoice-card-total {
    font-weight: 600;
  }

  .invoice-card-client {
    color: var(--color-text);
    font-weight: 500;
    margin-bottom: var(--space-1);
  }

  .invoice-card-items {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-bottom: var(--space-2);
  }

  .invoice-card-date {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .invoice-card-actions {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
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

  .text-overdue {
    color: var(--color-danger);
    font-weight: 500;
  }

  @media (max-width: 768px) {
    .invoice-cards {
      display: grid;
    }
  }
</style>
