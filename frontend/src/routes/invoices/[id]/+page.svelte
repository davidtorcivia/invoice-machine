<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { invoicesApi, emailApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import InvoiceClientCard from '$lib/components/invoices/InvoiceClientCard.svelte';
  import InvoiceDetailHeader from '$lib/components/invoices/InvoiceDetailHeader.svelte';
  import InvoiceLineItemsSummaryCard from '$lib/components/invoices/InvoiceLineItemsSummaryCard.svelte';
  import InvoiceSidebarDetailsCard from '$lib/components/invoices/InvoiceSidebarDetailsCard.svelte';
  import InvoiceStatusBanner from '$lib/components/invoices/InvoiceStatusBanner.svelte';
  import SendInvoiceEmailModal from '$lib/components/invoices/SendInvoiceEmailModal.svelte';

  $: invoiceId = $page.params.id || '';

  let invoice = null;
  let items = [];
  let loading = true;
  let generatingPdf = false;
  let showDeleteModal = false;
  let deleting = false;
  let showConvertModal = false;
  let converting = false;
  let showSendEmailModal = false;
  let emailLoading = false;
  let emailSending = false;
  let emailRecipient = '';
  let emailSubject = '';
  let emailBody = '';

  $: if (invoiceId) loadInvoice();
  $: isQuote = invoice?.document_type === 'quote';
  $: documentLabel = isQuote ? 'Quote' : 'Invoice';

  async function loadInvoice() {
    loading = true;
    try {
      const data = await invoicesApi.get(invoiceId);
      invoice = data;
      items = data.items || [];
    } catch (error) {
      toast.error('Failed to load invoice');
    } finally {
      loading = false;
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
      await invoicesApi.update(invoiceId, { document_type: 'invoice' });
      toast.success('Quote converted to invoice');
      await loadInvoice();
    } catch (error) {
      toast.error('Failed to convert quote');
    } finally {
      converting = false;
      showConvertModal = false;
    }
  }

  function cancelConvert() {
    showConvertModal = false;
  }

  async function openSendEmailModal() {
    showSendEmailModal = true;
    emailLoading = true;
    emailRecipient = invoice?.client_email || '';

    try {
      const preview = await emailApi.previewEmail(invoiceId, {});
      emailSubject = preview.subject;
      emailBody = preview.body;
    } catch (error) {
      toast.error('Failed to load email preview');
      showSendEmailModal = false;
    } finally {
      emailLoading = false;
    }
  }

  function cancelSendEmail() {
    showSendEmailModal = false;
    emailSubject = '';
    emailBody = '';
    emailRecipient = '';
  }

  async function confirmSendEmail() {
    if (!emailRecipient) {
      toast.error('Recipient email is required');
      return;
    }

    emailSending = true;
    try {
      await emailApi.sendInvoice(invoiceId, {
        recipient_email: emailRecipient,
        subject: emailSubject,
        body: emailBody
      });
      toast.success('Email sent successfully');
      cancelSendEmail();
      await loadInvoice();
    } catch (error) {
      toast.error(error.message || 'Failed to send email');
    } finally {
      emailSending = false;
    }
  }
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
      on:generatepdf={generatePdf}
      on:downloadpdf={downloadPdf}
      on:sendemail={openSendEmailModal}
    />

    <div class="invoice-layout">
      <div class="invoice-main">
        <InvoiceStatusBanner
          status={invoice.status}
          {isQuote}
          on:statuschange={(event) => updateStatus(event.detail)}
          on:convert={openConvertModal}
          on:delete={openDeleteModal}
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
  message="Convert quote #{invoice?.invoice_number} to an invoice? The document number will remain the same."
  confirmText="Convert"
  cancelText="Cancel"
  variant="primary"
  icon="check"
  loading={converting}
  onConfirm={confirmConvert}
  onCancel={cancelConvert}
/>

<SendInvoiceEmailModal
  show={showSendEmailModal}
  {documentLabel}
  {emailLoading}
  {emailSending}
  bind:emailRecipient
  bind:emailSubject
  bind:emailBody
  on:cancel={cancelSendEmail}
  on:confirm={confirmSendEmail}
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
