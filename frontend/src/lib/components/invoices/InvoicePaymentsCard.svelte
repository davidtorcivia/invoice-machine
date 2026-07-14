<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { paymentsApi } from '$lib/api';
  import { formatCurrency, formatDate, toast } from '$lib/stores';

  export let invoice;
  const dispatch = createEventDispatcher();
  /** @type {{payments: Array<Record<string, any>>, summary: Record<string, any> | null}} */
  let ledger = { payments: [], summary: null };
  let amount = '';
  let notes = '';
  let saving = false;
  let onlineResult = null;

  onMount(load);

  async function load() {
    try {
      ledger = await paymentsApi.forInvoice(invoice.id);
    } catch (error) {
      toast.error(error.message || 'Failed to load payments');
    }
  }

  async function recordPayment() {
    saving = true;
    try {
      await paymentsApi.recordManual(invoice.id, { amount, notes: notes || null });
      amount = '';
      notes = '';
      toast.success('Payment recorded');
      await load();
      dispatch('change');
    } catch (error) {
      toast.error(error.message || 'Failed to record payment');
    } finally {
      saving = false;
    }
  }

  async function toggleOnline() {
    saving = true;
    try {
      onlineResult = await paymentsApi.configureOnline(invoice.id, {
        enabled: !invoice.online_payment_enabled
      });
      toast.success(onlineResult.enabled ? 'Online payment link enabled' : 'Online payment link disabled');
      dispatch('change');
    } catch (error) {
      toast.error(error.message || 'Could not update payment link');
    } finally {
      saving = false;
    }
  }

  async function copyLink() {
    const url = onlineResult?.payment_url;
    if (!url) return;
    await navigator.clipboard.writeText(url);
    toast.success('Payment link copied');
  }
</script>

<div class="card payments-card">
  <div class="card-header">
    <div>
      <h3 class="card-title">Payments</h3>
      <p class="muted">Manual payments work without an online provider.</p>
    </div>
    {#if ledger.summary}
      <strong>{formatCurrency(ledger.summary.outstanding, invoice.currency_code)} due</strong>
    {/if}
  </div>

  {#if ledger.summary && Number(ledger.summary.outstanding) > 0 && !['draft', 'cancelled'].includes(invoice.status)}
    <form class="payment-form" on:submit|preventDefault={recordPayment}>
      <label>Amount<input type="number" min="0.01" step="0.01" max={ledger.summary.outstanding} bind:value={amount} required /></label>
      <label>Note (optional)<input bind:value={notes} maxlength="2000" placeholder="Bank transfer, check number…" /></label>
      <button class="btn btn-primary" disabled={saving}>Record payment</button>
    </form>
  {/if}

  {#if ledger.payments.length}
    <div class="timeline">
      {#each ledger.payments as payment}
        <div class="payment-row">
          <div><strong>{formatCurrency(payment.amount, payment.currency_code)}</strong><span>{payment.provider} · {payment.status}</span></div>
          <span>{formatDate(payment.occurred_at)}</span>
        </div>
      {/each}
    </div>
  {:else}
    <p class="empty">No payments recorded.</p>
  {/if}

  {#if !['paid', 'cancelled'].includes(invoice.status)}
    <div class="online-row">
      <div><strong>Online payment link</strong><span>Optional; requires a provider configured in Settings.</span></div>
      <button class="btn btn-secondary" disabled={saving} on:click={toggleOnline}>
        {invoice.online_payment_enabled ? 'Disable' : 'Enable'}
      </button>
    </div>
    {#if onlineResult?.payment_url}
      <button class="payment-link" on:click={copyLink}>{onlineResult.payment_url}</button>
    {/if}
  {/if}
</div>

<style>
  .payments-card { display: grid; gap: var(--space-4); }
  .card-header, .payment-row, .online-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); }
  .card-title, .muted, .empty { margin: 0; }
  .muted, .empty, .payment-row span, .online-row span { color: var(--color-text-secondary); font-size: .875rem; }
  .payment-form { display: grid; grid-template-columns: minmax(8rem, .5fr) 1fr auto; align-items: end; gap: var(--space-3); }
  label, .payment-row div, .online-row div { display: grid; gap: var(--space-1); }
  input { width: 100%; }
  .timeline { border-top: 1px solid var(--color-border); }
  .payment-row { padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); }
  .online-row { padding-top: var(--space-2); }
  .payment-link { background: var(--color-bg); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-2); color: var(--color-primary); text-align: left; overflow-wrap: anywhere; }
  @media (max-width: 720px) { .payment-form { grid-template-columns: 1fr; } }
</style>
