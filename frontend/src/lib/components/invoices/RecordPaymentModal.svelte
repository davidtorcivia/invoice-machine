<script>
  import { self, preventDefault } from 'svelte/legacy';
  import { formatCurrency } from '$lib/stores';

  /**
   * @typedef {Object} Props
   * @property {(detail?: any) => void} [oncancel]
   * @property {(detail?: any) => void} [onsave]
   * @property {boolean} [open]
   * @property {string} [currencyCode]
   * @property {string} [amountDue]
   * @property {boolean} [saving]
   */

  /** @type {Props} */
  let {
    open = false,
    currencyCode = 'USD',
    amountDue = '0',
    saving = false, oncancel, onsave } = $props();

  const METHODS = [
    { value: 'bank_transfer', label: 'Bank transfer' },
    { value: 'card', label: 'Card' },
    { value: 'cash', label: 'Cash' },
    { value: 'cheque', label: 'Cheque' },
    { value: 'paypal', label: 'PayPal' },
    { value: 'stripe', label: 'Stripe' },
    { value: 'other', label: 'Other' }
  ];

  let amount = $state('');
  let paymentDate = $state(new Date().toISOString().slice(0, 10));
  let method = $state('bank_transfer');
  let reference = $state('');
  let notes = $state('');
  let allowOverpayment = $state(false);
  let error = $state('');
  /** @type {HTMLInputElement | undefined} */
  let amountInput = $state();

  let dueNum = $derived(parseFloat(amountDue) || 0);
  let amountNum = $derived(parseFloat(amount) || 0);
  let exceedsBalance = $derived(amountNum > dueNum);

  let wasOpen = $state(false);
  $effect(() => {
    if (open && !wasOpen) {
      const due = parseFloat(amountDue) || 0;
      amount = due > 0 ? due.toFixed(2) : '';
      paymentDate = new Date().toISOString().slice(0, 10);
      method = 'bank_transfer';
      reference = '';
      notes = '';
      allowOverpayment = false;
      error = '';
      queueMicrotask(() => {
        amountInput?.focus();
        amountInput?.select();
      });
    }
    wasOpen = open;
  });

  function submit() {
    error = '';
    if (!(amountNum > 0)) {
      error = 'Enter an amount greater than zero.';
      return;
    }
    if (exceedsBalance && !allowOverpayment) {
      error = 'That is more than the balance due. Tick "record as overpayment" to continue.';
      return;
    }
    onsave?.({
      amount: amountNum,
      payment_date: paymentDate,
      method,
      reference: reference.trim() || null,
      notes: notes.trim() || null,
      allow_overpayment: allowOverpayment
    });
  }

  function onKeydown(event) {
    if (event.key === 'Escape') oncancel?.();
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="modal-backdrop"
    role="presentation"
    onclick={self(() => oncancel?.())}
  >
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="record-payment-title">
      <div class="modal-header">
        <h2 id="record-payment-title">Record payment</h2>
        <button
          type="button"
          class="modal-close"
          onclick={() => oncancel?.()}
          aria-label="Close"
        >&times;</button>
      </div>

      <form onsubmit={preventDefault(submit)}>
        <div class="modal-body">
          <p class="due-hint">
            Balance due: <strong>{formatCurrency(amountDue, currencyCode)}</strong>
          </p>

          <div class="form-group">
            <label for="payment-amount" class="label">Amount ({currencyCode})</label>
            <input
              id="payment-amount"
              bind:this={amountInput}
              bind:value={amount}
              type="number"
              class="input"
              step="0.01"
              min="0.01"
              required
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="payment-date" class="label">Date received</label>
              <input id="payment-date" bind:value={paymentDate} type="date" class="input" required />
            </div>

            <div class="form-group">
              <label for="payment-method" class="label">Method</label>
              <select id="payment-method" bind:value={method} class="select">
                {#each METHODS as option}
                  <option value={option.value}>{option.label}</option>
                {/each}
              </select>
            </div>
          </div>

          <div class="form-group">
            <label for="payment-reference" class="label">Reference</label>
            <input
              id="payment-reference"
              bind:value={reference}
              type="text"
              class="input"
              maxlength="255"
              placeholder="Bank reference, cheque number, transaction ID"
            />
          </div>

          <div class="form-group">
            <label for="payment-notes" class="label">Notes</label>
            <textarea
              id="payment-notes"
              bind:value={notes}
              class="textarea"
              rows="2"
              maxlength="2000"
            ></textarea>
          </div>

          {#if exceedsBalance}
            <label class="checkbox-row">
              <input type="checkbox" bind:checked={allowOverpayment} />
              <span>Record as overpayment (more than the balance due)</span>
            </label>
          {/if}

          {#if error}
            <p class="form-error" role="alert">{error}</p>
          {/if}
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" onclick={() => oncancel?.()}>
            Cancel
          </button>
          <button type="submit" class="btn btn-primary" disabled={saving}>
            {saving ? 'Saving...' : 'Record payment'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .due-hint {
    margin: 0 0 1rem;
    color: var(--color-text-muted);
    font-size: 0.9rem;
  }

  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.88rem;
  }

  .form-error {
    margin: 0.75rem 0 0;
    color: var(--color-danger, #dc2626);
    font-size: 0.85rem;
  }
</style>
