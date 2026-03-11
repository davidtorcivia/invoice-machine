<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { invoicesApi, profileApi } from '$lib/api';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import InvoiceEditDetailsCard from '$lib/components/invoices/InvoiceEditDetailsCard.svelte';
  import InvoiceLineItemsCard from '$lib/components/invoices/InvoiceLineItemsCard.svelte';
  import InvoiceNotesCard from '$lib/components/invoices/InvoiceNotesCard.svelte';
  import InvoicePaymentInstructionsCard from '$lib/components/invoices/InvoicePaymentInstructionsCard.svelte';
  import InvoiceTaxCard from '$lib/components/invoices/InvoiceTaxCard.svelte';
  import InvoiceTypeCard from '$lib/components/invoices/InvoiceTypeCard.svelte';

  $: invoiceId = $page.params.id || '';

  /**
   * @typedef {{ id: string, name: string, instructions?: string }} PaymentMethod
   * @typedef {{ id?: number|string, description: string, quantity: number, unit_type: string, unit_price: string|number }} InvoiceItemDraft
   */

  let invoice = null;
  let profile = null;
  let loading = true;
  let saving = false;
  let showDiscardModal = false;

  // Form data
  let issueDate = '';
  let dueDate = '';
  let paymentTermsDays = 30;
  let notes = '';
  let status = 'draft';
  let documentType = 'invoice';
  let clientReference = '';
  let showPaymentInstructions = true;
  /** @type {string[]} */
  let selectedPaymentMethods = [];
  /** @type {InvoiceItemDraft[]} */
  let items = [];

  // Notes handling
  let useDefaultNotes = false;
  let originalNotes = '';
  let defaultNotesInitialized = false;

  // Tax settings
  let taxEnabled = false;
  let taxRate = '';
  let taxName = 'Tax';

  // Default notes from profile
  $: defaultNotesText = profile?.default_notes || '';

  onMount(async () => {
    await Promise.all([loadInvoice(), loadProfile()]);
  });

  async function loadProfile() {
    try {
      profile = await profileApi.get();
    } catch (error) {
      console.error('Failed to load profile');
    }
  }

  // Parse payment methods from profile
  /** @type {PaymentMethod[]} */
  $: availablePaymentMethods = parseJsonArray(profile?.payment_methods);

  async function loadInvoice() {
    loading = true;
    try {
      const data = await invoicesApi.get(invoiceId);
      invoice = data;

      // Populate form
      issueDate = data.issue_date || '';
      dueDate = data.due_date || '';
      paymentTermsDays = data.payment_terms_days || 30;
      notes = data.notes || '';
      status = data.status || 'draft';
      documentType = data.document_type || 'invoice';
      clientReference = data.client_reference || '';
      showPaymentInstructions = data.show_payment_instructions !== false;
      selectedPaymentMethods = parseJsonArray(data.selected_payment_methods);
      items = (data.items || []).map(item => ({
        id: item.id,
        description: item.description,
        quantity: item.quantity,
        unit_type: item.unit_type || 'qty',
        unit_price: item.unit_price,
      }));

      if (items.length === 0) {
        items = [{ description: '', quantity: 1, unit_price: '', unit_type: 'qty' }];
      }

      // Load tax settings
      taxEnabled = data.tax_enabled || false;
      taxRate = data.tax_rate && parseFloat(data.tax_rate) > 0 ? data.tax_rate : '';
      taxName = data.tax_name || 'Tax';

      // Track original notes and check if using default
      originalNotes = data.notes || '';
    } catch (error) {
      toast.error('Failed to load invoice');
      goto('/invoices');
    } finally {
      loading = false;
    }
  }

  // Effective notes (use default if toggled on)
  $: effectiveNotes = useDefaultNotes && defaultNotesText ? defaultNotesText : notes;
  $: if (!defaultNotesInitialized && profile && invoice) {
    useDefaultNotes = !!(profile.default_notes && originalNotes === profile.default_notes);
    defaultNotesInitialized = true;
  }

  async function saveInvoice() {
    const validItems = items.filter(item => item.description.trim() && item.unit_price);
    if (validItems.length === 0) {
      toast.error('Please add at least one line item');
      return;
    }

    saving = true;
    try {
      // Update invoice details
      await invoicesApi.update(invoiceId, {
        issue_date: issueDate || undefined,
        due_date: dueDate || undefined,
        payment_terms_days: Number(paymentTermsDays) || undefined,
        notes: effectiveNotes || undefined,
        status: status,
        document_type: documentType,
        client_reference: clientReference || undefined,
        show_payment_instructions: showPaymentInstructions,
        selected_payment_methods: stringifyJsonArray(selectedPaymentMethods),
        tax_enabled: taxEnabled ? 1 : 0,
        tax_rate: taxEnabled && taxRate ? parseFloat(taxRate) : 0,
        tax_name: taxName || 'Tax',
      });

      // Delete removed items
      const originalItemIds = new Set((invoice.items || []).map((item) => item.id));
      const currentItemIds = new Set(items.filter((item) => item.id).map((item) => item.id));

      for (const itemId of originalItemIds) {
        if (!currentItemIds.has(itemId)) {
          await invoicesApi.deleteItem(invoiceId, itemId);
        }
      }

      // Update existing items and add new ones
      for (let i = 0; i < validItems.length; i++) {
        const item = validItems[i];
        if (item.id) {
          await invoicesApi.updateItem(invoiceId, item.id, {
            description: item.description,
            quantity: Number(item.quantity) || 1,
            unit_type: item.unit_type || 'qty',
            unit_price: Number(item.unit_price) || 0,
            sort_order: i,
          });
        } else {
          await invoicesApi.addItem(invoiceId, {
            description: item.description,
            quantity: Number(item.quantity) || 1,
            unit_type: item.unit_type || 'qty',
            unit_price: Number(item.unit_price) || 0,
            sort_order: i,
          });
        }
      }

      toast.success('Invoice updated successfully');
      goto(`/invoices/${invoiceId}`);
    } catch (error) {
      toast.error('Failed to update invoice');
    } finally {
      saving = false;
    }
  }

  function cancel() {
    showDiscardModal = true;
  }

  function confirmDiscard() {
    showDiscardModal = false;
    goto(`/invoices/${invoiceId}`);
  }
</script>

<Header
  title={invoice ? `Edit Invoice #${invoice.invoice_number}` : 'Edit Invoice'}
  subtitle={invoice ? (invoice.client_business || invoice.client_name || '') : ''}
/>

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <form on:submit|preventDefault={saveInvoice} class="form-layout">
      <InvoiceTypeCard
        bind:documentType
        helpText="Changing document type will not regenerate the number. Create a new document if you need a different number format."
      />

      <InvoiceEditDetailsCard
        {invoice}
        bind:documentType
        bind:issueDate
        bind:dueDate
        bind:paymentTermsDays
        bind:status
        bind:clientReference
      />

      <InvoiceLineItemsCard bind:items bind:taxEnabled bind:taxRate bind:taxName />

      <InvoiceTaxCard
        bind:taxEnabled
        bind:taxRate
        bind:taxName
        enabledHint="This will override any client or global default tax settings."
      />

      <InvoicePaymentInstructionsCard
        {availablePaymentMethods}
        bind:selectedPaymentMethods
        bind:showPaymentInstructions
      />

      <InvoiceNotesCard bind:useDefaultNotes {defaultNotesText} bind:notes />

      <!-- Actions -->
      <div class="form-actions">
        <button
          type="button"
          class="btn btn-secondary"
          on:click={cancel}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          type="submit"
          class="btn btn-primary"
          disabled={saving}
        >
          <Icon name="check" size="sm" />
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </form>
  {/if}
</div>

<ConfirmModal
  show={showDiscardModal}
  title="Discard Changes?"
  message="Are you sure you want to discard your changes?"
  confirmText="Discard"
  icon="warning"
  variant="warning"
  onConfirm={confirmDiscard}
  onCancel={() => showDiscardModal = false}
/>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 900px;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .form-layout {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  /* Responsive - Large screens */
  @media (min-width: 1400px) {
    .page-content {
      max-width: 1100px;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }
  }

  /* Responsive - Small screens */
  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .form-actions {
      flex-direction: column-reverse;
    }

    .form-actions .btn {
      width: 100%;
    }
  }
</style>
