<script>
  import { run } from 'svelte/legacy';

  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { invoicesApi, paymentsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import InvoiceClientCard from '$lib/components/invoices/InvoiceClientCard.svelte';
  import InvoiceConversionLinkCard from '$lib/components/invoices/InvoiceConversionLinkCard.svelte';
  import InvoiceDetailHeader from '$lib/components/invoices/InvoiceDetailHeader.svelte';
  import InvoiceEmailSender from '$lib/components/invoices/InvoiceEmailSender.svelte';
  import InvoiceLineItemsSummaryCard from '$lib/components/invoices/InvoiceLineItemsSummaryCard.svelte';
  import InvoicePayOnlineCard from '$lib/components/invoices/InvoicePayOnlineCard.svelte';
  import InvoicePaymentsCard from '$lib/components/invoices/InvoicePaymentsCard.svelte';
  import InvoiceSidebarDetailsCard from '$lib/components/invoices/InvoiceSidebarDetailsCard.svelte';
  import InvoiceStatusBanner from '$lib/components/invoices/InvoiceStatusBanner.svelte';
  import RecordPaymentModal from '$lib/components/invoices/RecordPaymentModal.svelte';

  let invoice = $state(/** @type {import('$lib/types').Invoice|null} */ (null));
  let items = $state([]);
  let loading = $state(true);
  let loadError = false;
  let generatingPdf = $state(false);
  let showDeleteModal = $state(false);
  let deleting = $state(false);
  let showConvertModal = $state(false);
  let converting = $state(false);
  let emailSender = $state(/** @type {any} */ (null));
  let payments = $state([]);
  let showRecordPaymentModal = $state(false);
  let savingPayment = $state(false);
  let paymentsBusy = $state(false);
  let deletePaymentTarget = $state(/** @type {any} */ (null));

  async function loadInvoice() {
    loading = true;
    loadError = false;
    try {
      const data = await invoicesApi.get(invoiceId);
      invoice = data;
      items = data.items || [];
      await loadPayments();
    } catch (error) {
      loadError = true;
      toast.error('Failed to load invoice');
    } finally {
      loading = false;
    }
  }

  async function loadPayments() {
    // Quotes are not owed, so they carry no payment ledger.
    if (isQuote) {
      payments = [];
      return;
    }
    try {
      const data = await paymentsApi.list(invoiceId);
      payments = data.payments || [];
      if (invoice) {
        invoice = { ...invoice, amount_paid: data.amount_paid, amount_due: data.amount_due };
      }
    } catch (error) {
      payments = [];
    }
  }

  async function savePayment(detail) {
    savingPayment = true;
    try {
      await paymentsApi.record(invoiceId, detail);
      toast.success('Payment recorded');
      showRecordPaymentModal = false;
      await loadInvoice();
    } catch (error) {
      toast.error(error.message || 'Failed to record payment');
    } finally {
      savingPayment = false;
    }
  }

  async function confirmDeletePayment() {
    if (!deletePaymentTarget) return;
    paymentsBusy = true;
    try {
      await paymentsApi.delete(deletePaymentTarget.id);
      toast.success('Payment deleted');
      await loadInvoice();
    } catch (error) {
      toast.error(error.message || 'Failed to delete payment');
    } finally {
      paymentsBusy = false;
      deletePaymentTarget = null;
    }
  }

  async function generatePdf() {
    generatingPdf = true;
    try {
      const result = await invoicesApi.generatePdf(invoiceId);
      toast.success('PDF generated successfully');
      window.open(result.pdf_url, '_blank');
    } catch (error) {
      toast.error('Failed to generate PDF');
    } finally {
      generatingPdf = false;
    }
  }

  function downloadPdf() {
    window.open(invoicesApi.getPdfUrl(invoiceId), '_blank');
  }

  async function updateStatus(status) {
    try {
      await invoicesApi.update(invoiceId, { status });
      toast.success(`Invoice marked as ${status}`);
      await loadInvoice();
    } catch (error) {
      toast.error('Failed to update status');
    }
  }

  function openDeleteModal() {
    showDeleteModal = true;
  }

  async function confirmDelete() {
    deleting = true;
    try {
      await invoicesApi.delete(invoiceId);
      toast.success('Invoice moved to trash');
      goto('/invoices');
    } catch (error) {
      toast.error('Failed to delete invoice');
    } finally {
      deleting = false;
    }
  }

  function cancelDelete() {
    showDeleteModal = false;
  }

  function openConvertModal() {
    showConvertModal = true;
  }

  async function confirmConvert() {
    converting = true;
    try {
      // Creates a linked invoice and leaves the quote intact, so there is still
      // a record of exactly what the client accepted.
      const created = await invoicesApi.convertQuote(invoiceId);
      toast.success(`Created invoice ${created.invoice_number}`);
      await goto(`/invoices/${created.id}`);
    } catch (error) {
      toast.error(error.message || 'Failed to convert quote');
    } finally {
      converting = false;
      showConvertModal = false;
    }
  }

  function cancelConvert() {
    showConvertModal = false;
  }

  let invoiceId = $derived($page.params.id || '');
  run(() => {
    if (invoiceId) loadInvoice();
  });
  let isQuote = $derived(invoice?.document_type === 'quote');
  let documentLabel = $derived(isQuote ? 'Quote' : 'Invoice');
</script>

<Header title={invoice ? `${documentLabel} #${invoice.invoice_number}` : 'Invoice'} />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if invoice}
    <InvoiceDetailHeader
      {invoiceId}
      {invoice}
      {documentLabel}
      {generatingPdf}
      ongeneratepdf={generatePdf}
      ondownloadpdf={downloadPdf}
      onsendemail={() => emailSender?.open()}
    />

    <div class="invoice-layout">
      <div class="invoice-main">
        <InvoiceStatusBanner
          status={invoice.status}
          {isQuote}
          onstatuschange={(detail) => updateStatus(detail)}
          onconvert={openConvertModal}
          ondelete={openDeleteModal}
        />
        <InvoiceClientCard {invoice} />
        <InvoiceLineItemsSummaryCard {invoice} {items} />

        {#if invoice.notes}
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Notes</h3>
            </div>
            <p class="notes-text">{invoice.notes}</p>
          </div>
        {/if}
      </div>

      <div class="invoice-sidebar">
        <InvoiceSidebarDetailsCard {invoice} {documentLabel} {isQuote} />

        {#if !isQuote}
          <InvoicePaymentsCard
            {payments}
            currencyCode={invoice.currency_code}
            total={invoice.total}
            amountPaid={invoice.amount_paid}
            amountDue={invoice.amount_due}
            busy={paymentsBusy}
            onrecord={() => (showRecordPaymentModal = true)}
            ondelete={(detail) => (deletePaymentTarget = detail)}
          />

          <InvoicePayOnlineCard {invoiceId} {invoice} onupdated={loadInvoice} />
        {/if}

        <InvoiceConversionLinkCard {invoice} />
      </div>
    </div>
  {:else}
    <div class="error-state">
      <p class="error-title">This {documentLabel.toLowerCase()} could not be loaded.</p>
      <p class="error-hint">It may have been deleted, or the connection failed.</p>
      <div class="error-actions">
        <button class="btn btn-secondary" onclick={loadInvoice}>Retry</button>
        <button class="btn btn-primary" onclick={() => goto('/invoices')}>Back to Invoices</button>
      </div>
    </div>
  {/if}
</div>

<ConfirmModal
  show={showDeleteModal}
  title="Delete {documentLabel}"
  message="Move {documentLabel.toLowerCase()} #{invoice?.invoice_number} to trash? You can restore it later from the Trash."
  confirmText="Delete"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deleting}
  onConfirm={confirmDelete}
  onCancel={cancelDelete}
/>

<ConfirmModal
  show={showConvertModal}
  title="Convert to Invoice"
  message="Create an invoice from quote {invoice?.invoice_number}? The quote is kept as a record of what was accepted, and the new invoice is linked to it."
  confirmText="Create invoice"
  cancelText="Cancel"
  variant="primary"
  icon="check"
  loading={converting}
  onConfirm={confirmConvert}
  onCancel={cancelConvert}
/>

<RecordPaymentModal
  open={showRecordPaymentModal}
  currencyCode={invoice?.currency_code || 'USD'}
  amountDue={invoice?.amount_due || '0'}
  saving={savingPayment}
  onsave={savePayment}
  oncancel={() => (showRecordPaymentModal = false)}
/>

<ConfirmModal
  show={!!deletePaymentTarget}
  title="Delete payment"
  message="Delete this payment? The invoice balance will be recalculated, and a fully paid invoice will revert to unpaid."
  confirmText="Delete"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={paymentsBusy}
  onConfirm={confirmDeletePayment}
  onCancel={() => (deletePaymentTarget = null)}
/>

<InvoiceEmailSender
  bind:this={emailSender}
  {invoiceId}
  {invoice}
  {documentLabel}
  onsent={loadInvoice}
/>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 1400px;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .error-state {
    text-align: center;
    padding: var(--space-12);
  }

  .error-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0 0 var(--space-2);
  }

  .error-hint {
    color: var(--color-text-secondary);
    margin: 0 0 var(--space-6);
  }

  .error-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: center;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }

  .invoice-layout {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: var(--space-6);
  }

  .invoice-main {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .invoice-sidebar {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .notes-text {
    white-space: pre-line;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  @media (max-width: 1024px) {
    .invoice-layout {
      grid-template-columns: 1fr;
    }

    .invoice-sidebar {
      order: -1;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }
  }

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
