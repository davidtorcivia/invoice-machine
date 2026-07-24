<script>
  import { formatCurrency, formatDate } from '$lib/stores';

  /** @type {{ as_of?: string, by_currency?: Record<string, any>, invoices?: any[] } | null} */
  export let aging = null;

  const BUCKET_LABELS = {
    current: 'Not yet due',
    '1_30': '1-30 days',
    '31_60': '31-60 days',
    '61_90': '61-90 days',
    over_90: 'Over 90 days'
  };

  const BUCKET_ORDER = ['current', '1_30', '31_60', '61_90', 'over_90'];

  $: byCurrency = aging?.by_currency || {};
  $: currencies = Object.keys(byCurrency);
  $: overdueInvoices = (aging?.invoices || []).filter((invoice) => invoice.days_overdue > 0);
</script>

<div class="card">
  <div class="card-header">
    <div>
      <h2 class="card-title">Accounts receivable</h2>
      <p class="card-subtitle">
        Outstanding balances by how far past due, as of {formatDate(aging?.as_of)}
      </p>
    </div>
  </div>

  <div class="card-body">
    {#if currencies.length === 0}
      <p class="empty">Nothing outstanding. Every issued invoice has been paid.</p>
    {:else}
      {#each currencies as currency (currency)}
        {@const data = byCurrency[currency]}
        <div class="currency-block">
          {#if currencies.length > 1}
            <h3 class="currency-heading">{currency}</h3>
          {/if}

          <div class="bucket-grid">
            {#each BUCKET_ORDER as bucket (bucket)}
              <div class="bucket" class:severe={bucket === 'over_90' && parseFloat(data.buckets[bucket]) > 0}>
                <span class="bucket-label">{BUCKET_LABELS[bucket]}</span>
                <span class="bucket-value">{formatCurrency(data.buckets[bucket], currency)}</span>
                <span class="bucket-count">
                  {data.counts[bucket]} invoice{data.counts[bucket] === 1 ? '' : 's'}
                </span>
              </div>
            {/each}
          </div>

          <p class="currency-total">
            Total outstanding:
            <strong>{formatCurrency(data.total_outstanding, currency)}</strong>
            across {data.invoice_count} invoice{data.invoice_count === 1 ? '' : 's'}
          </p>
        </div>
      {/each}

      {#if overdueInvoices.length > 0}
        <div class="table-scroll">
          <table class="table">
            <thead>
              <tr>
                <th scope="col">Invoice</th>
                <th scope="col">Client</th>
                <th scope="col">Due</th>
                <th scope="col" class="numeric">Days overdue</th>
                <th scope="col" class="numeric">Balance</th>
              </tr>
            </thead>
            <tbody>
              {#each overdueInvoices as invoice (invoice.invoice_id)}
                <tr>
                  <td>
                    <a href="/invoices/{invoice.invoice_id}">{invoice.invoice_number}</a>
                  </td>
                  <td>{invoice.client_name || 'No client'}</td>
                  <td>{formatDate(invoice.due_date)}</td>
                  <td class="numeric">{invoice.days_overdue}</td>
                  <td class="numeric">
                    {formatCurrency(invoice.amount_due, invoice.currency_code)}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .card-subtitle {
    margin: var(--space-1) 0 0;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .empty {
    margin: 0;
    color: var(--color-text-secondary);
    font-size: 0.9rem;
  }

  .currency-block + .currency-block {
    margin-top: var(--space-6);
  }

  .currency-heading {
    margin: 0 0 var(--space-3);
    font-size: 0.9rem;
    font-weight: 600;
  }

  .bucket-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: var(--space-3);
  }

  .bucket {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md, 6px);
  }

  .bucket.severe {
    border-color: var(--color-danger, #dc2626);
  }

  .bucket-label {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }

  .bucket-value {
    font-size: 1.05rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .bucket-count {
    font-size: 0.72rem;
    color: var(--color-text-secondary);
  }

  .currency-total {
    margin: var(--space-3) 0 0;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
  }

  .table-scroll {
    margin-top: var(--space-6);
    overflow-x: auto;
  }

  .numeric {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
</style>
