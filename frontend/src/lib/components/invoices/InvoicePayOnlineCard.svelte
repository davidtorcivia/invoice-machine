<script>
  import { invoicesApi } from '$lib/api';
  import { toast } from '$lib/stores';

  let { invoiceId, invoice, onupdated = () => {} } = $props();

  let creatingPaymentLink = $state(false);

  async function createPaymentLink() {
    creatingPaymentLink = true;
    try {
      await invoicesApi.createPaymentLink(invoiceId);
      toast.success(invoice.payment_link_url ? 'Payment link updated' : 'Payment link created');
      await onupdated();
    } catch (error) {
      toast.error(error.message || 'Failed to create payment link');
    } finally {
      creatingPaymentLink = false;
    }
  }

  async function copyPaymentLink() {
    if (!invoice?.payment_link_url) return;
    try {
      await navigator.clipboard.writeText(invoice.payment_link_url);
      toast.success('Payment link copied');
    } catch (error) {
      toast.error('Could not copy the link');
    }
  }
</script>

<div class="card">
  <div class="card-header">
    <h2 class="card-title">Pay online</h2>
  </div>
  <div class="card-body">
    {#if invoice.payment_link_url}
      <p class="link-hint">
        Share this link so the client can pay by card. It does not expire and
        always charges what is still due.
      </p>
      <div class="link-actions">
        <a
          href={invoice.payment_link_url}
          target="_blank"
          rel="noopener noreferrer"
          class="btn btn-secondary btn-sm"
        >Open</a>
        <button type="button" class="btn btn-secondary btn-sm" onclick={copyPaymentLink}>
          Copy link
        </button>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          onclick={createPaymentLink}
          disabled={creatingPaymentLink}
          title="Point the link at the current app base URL, after a domain change"
        >
          {creatingPaymentLink ? 'Updating...' : 'Update link'}
        </button>
      </div>
    {:else}
      <p class="link-hint">
        Create a link the client can use to pay the outstanding balance by card.
        Requires online payments and the app base URL in settings.
      </p>
      <button
        type="button"
        class="btn btn-secondary btn-sm"
        onclick={createPaymentLink}
        disabled={creatingPaymentLink || parseFloat(invoice.amount_due) <= 0}
      >
        {creatingPaymentLink ? 'Creating...' : 'Create payment link'}
      </button>
    {/if}
  </div>
</div>

<style>
  .link-hint {
    margin: 0 0 0.75rem;
    color: var(--color-text-muted);
    font-size: 0.85rem;
    line-height: 1.5;
  }

  .link-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
</style>
