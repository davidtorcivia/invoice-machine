<script>
  import { emailApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import SendInvoiceEmailModal from './SendInvoiceEmailModal.svelte';

  let { invoiceId, invoice, documentLabel, onsent = () => {} } = $props();

  let show = $state(false);
  let emailLoading = $state(false);
  let emailSending = $state(false);
  let emailRecipient = $state('');
  let emailSubject = $state('');
  let emailBody = $state('');

  // Called by the page through bind:this.
  export async function open() {
    show = true;
    emailLoading = true;
    emailRecipient = invoice?.client_email || '';

    try {
      const preview = await emailApi.previewEmail(invoiceId, {});
      emailSubject = preview.subject;
      emailBody = preview.body;
    } catch (error) {
      toast.error('Failed to load email preview');
      show = false;
    } finally {
      emailLoading = false;
    }
  }

  function cancel() {
    show = false;
    emailSubject = '';
    emailBody = '';
    emailRecipient = '';
  }

  async function confirm() {
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
      cancel();
      await onsent();
    } catch (error) {
      toast.error(error.message || 'Failed to send email');
    } finally {
      emailSending = false;
    }
  }
</script>

<SendInvoiceEmailModal
  {show}
  {documentLabel}
  {emailLoading}
  {emailSending}
  bind:emailRecipient
  bind:emailSubject
  bind:emailBody
  oncancel={cancel}
  onconfirm={confirm}
/>
