<script>
  import { formatCurrency } from '$lib/stores';

  /** @type {{ currency: string, invoiced: string, paid: string, outstanding: string, coverage: any } | null} */
  export let consolidated = null;

  $: coverage = consolidated?.coverage;
  $: uncovered = Object.entries(coverage?.uncovered_by_currency || {});
</script>

{#if consolidated}
  <div class="card">
    <div class="card-header">
      <div>
        <h2 class="card-title">All currencies, converted</h2>
        <p class="card-subtitle">
          Every invoice converted to {consolidated.currency} using the rate recorded
          when it was issued
        </p>
      </div>
    </div>

    <div class="card-body">
      <div class="figures">
        <div class="figure">
          <span class="figure-label">Invoiced</span>
          <span class="figure-value">
            {formatCurrency(consolidated.invoiced, consolidated.currency)}
          </span>
        </div>
        <div class="figure">
          <span class="figure-label">Paid</span>
          <span class="figure-value">
            {formatCurrency(consolidated.paid, consolidated.currency)}
          </span>
        </div>
        <div class="figure">
          <span class="figure-label">Outstanding</span>
          <span class="figure-value">
            {formatCurrency(consolidated.outstanding, consolidated.currency)}
          </span>
        </div>
      </div>

      {#if coverage?.complete}
        <p class="coverage ok">
          All {coverage.total_invoices} invoices in this period were converted.
        </p>
      {:else}
        <p class="coverage warn" role="status">
          {coverage.uncovered_invoices} of {coverage.total_invoices} invoices are
          <strong>not included</strong> above: no exchange rate was recorded for
          {#each uncovered as [currency, count], index}
            {currency} ({count}){index < uncovered.length - 1 ? ', ' : ''}
          {/each}.
          Add rates under Settings to include them.
        </p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .card-subtitle {
    margin: var(--space-1) 0 0;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .figures {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: var(--space-4);
  }

  .figure {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .figure-label {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .figure-value {
    font-size: 1.3rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .coverage {
    margin: var(--space-4) 0 0;
    font-size: 0.82rem;
    line-height: 1.5;
  }

  .coverage.ok {
    color: var(--color-text-secondary);
  }

  .coverage.warn {
    padding: var(--space-3);
    border-radius: var(--radius-md, 6px);
    border: 1px solid var(--color-warning, #d97706);
    color: var(--color-text);
  }
</style>
