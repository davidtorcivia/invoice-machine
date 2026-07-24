<script>
  import { formatCurrency, formatDate } from '$lib/stores';
  import Icons from '$lib/components/Icons.svelte';

  
  /**
   * @typedef {Object} Props
   * @property {(detail?: any) => void} [ondelete]
   * @property {(detail?: any) => void} [onrecord]
   * @property {{ id: number, amount: string, currency_code: string, payment_date: string, method?: string|null, reference?: string|null, provider?: string|null }[]} [payments]
   * @property {string} [currencyCode]
   * @property {string} [total]
   * @property {string} [amountPaid]
   * @property {string} [amountDue]
   * @property {boolean} [busy]
   */

  /** @type {Props} */
  let {
    payments = [],
    currencyCode = 'USD',
    total = '0',
    amountPaid = '0',
    amountDue = '0',
    busy = false, ondelete, onrecord } = $props();

  const METHOD_LABELS = {
    bank_transfer: 'Bank transfer',
    card: 'Card',
    cash: 'Cash',
    cheque: 'Cheque',
    paypal: 'PayPal',
    stripe: 'Stripe',
    other: 'Other'
  };

  let paidNum = $derived(parseFloat(amountPaid) || 0);
  let totalNum = $derived(parseFloat(total) || 0);
  let dueNum = $derived(parseFloat(amountDue) || 0);
  let percentPaid = $derived(totalNum > 0 ? Math.min(100, Math.round((paidNum / totalNum) * 100)) : 0);
  let isSettled = $derived(dueNum <= 0 && paidNum > 0);

  function methodLabel(method) {
    if (!method) return 'Payment';
    return METHOD_LABELS[method] || method;
  }
</script>

<div class="card">
  <div class="card-header">
    <h2 class="card-title">Payments</h2>
    <button
      type="button"
      class="btn btn-secondary btn-sm"
      onclick={() => onrecord?.()}
      disabled={busy}
    >
      <Icons name="plus" size="sm" />
      Record payment
    </button>
  </div>

  <div class="card-body">
    <div class="balance">
      <div class="balance-row">
        <span class="balance-label">Invoice total</span>
        <span class="balance-value">{formatCurrency(total, currencyCode)}</span>
      </div>
      <div class="balance-row">
        <span class="balance-label">Paid to date</span>
        <span class="balance-value paid">{formatCurrency(amountPaid, currencyCode)}</span>
      </div>
      <div class="balance-row total">
        <span class="balance-label">Balance due</span>
        <span class="balance-value" class:settled={isSettled}>
          {formatCurrency(amountDue, currencyCode)}
        </span>
      </div>

      {#if paidNum > 0 && !isSettled}
        <div
          class="progress"
          role="progressbar"
          aria-valuenow={percentPaid}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-label="Percentage paid"
        >
          <div class="progress-bar" style="width: {percentPaid}%"></div>
        </div>
        <p class="progress-label">{percentPaid}% paid</p>
      {/if}
    </div>

    {#if payments.length === 0}
      <p class="empty">No payments recorded yet.</p>
    {:else}
      <ul class="payment-list">
        {#each payments as payment (payment.id)}
          <li class="payment">
            <div class="payment-main">
              <span class="payment-amount">
                {formatCurrency(payment.amount, payment.currency_code || currencyCode)}
              </span>
              <span class="payment-meta">
                {formatDate(payment.payment_date)} &middot; {methodLabel(payment.method)}
                {#if payment.reference}
                  &middot; <span class="payment-ref">{payment.reference}</span>
                {/if}
              </span>
            </div>
            <button
              type="button"
              class="btn-danger-text"
              onclick={() => ondelete?.(payment)}
              disabled={busy}
              aria-label="Delete payment of {payment.amount}"
            >
              Delete
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</div>

<style>
  .balance {
    padding-bottom: 1rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--color-border);
  }

  .balance-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.3rem 0;
    font-size: 0.9rem;
  }

  .balance-row.total {
    margin-top: 0.4rem;
    padding-top: 0.6rem;
    border-top: 1px solid var(--color-border);
    font-size: 1rem;
    font-weight: 600;
  }

  .balance-label {
    color: var(--color-text-muted);
  }

  .balance-value {
    font-variant-numeric: tabular-nums;
  }

  .balance-value.paid {
    color: var(--color-success, #16a34a);
  }

  .balance-value.settled {
    color: var(--color-success, #16a34a);
  }

  .progress {
    margin-top: 0.75rem;
    height: 6px;
    border-radius: 3px;
    background: var(--color-border);
    overflow: hidden;
  }

  .progress-bar {
    height: 100%;
    background: var(--color-success, #16a34a);
    transition: width 0.2s ease;
  }

  .progress-label {
    margin: 0.35rem 0 0;
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }

  .empty {
    margin: 0;
    color: var(--color-text-muted);
    font-size: 0.9rem;
  }

  .payment-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .payment {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .payment-main {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }

  .payment-amount {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .payment-meta {
    font-size: 0.8rem;
    color: var(--color-text-muted);
  }

  .payment-ref {
    font-family: var(--font-mono, monospace);
  }
</style>
