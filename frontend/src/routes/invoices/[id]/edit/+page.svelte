<script>
  import { run, preventDefault } from 'svelte/legacy';

  import { onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { invoicesApi, profileApi } from '$lib/api';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import { addDays, toast } from '$lib/stores';
  import { createUnsavedGuard } from '$lib/unsavedGuard';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import InvoiceEditDetailsCard from '$lib/components/invoices/InvoiceEditDetailsCard.svelte';
  import InvoiceLineItemsCard from '$lib/components/invoices/InvoiceLineItemsCard.svelte';
  import InvoiceNotesCard from '$lib/components/invoices/InvoiceNotesCard.svelte';
  import InvoicePaymentInstructionsCard from '$lib/components/invoices/InvoicePaymentInstructionsCard.svelte';
  import InvoiceTaxCard from '$lib/components/invoices/InvoiceTaxCard.svelte';
  import InvoiceTypeCard from '$lib/components/invoices/InvoiceTypeCard.svelte';

  let invoiceId = $derived($page.params.id || '');

  /**
   * @typedef {{ id: string, name: string, instructions?: string }} PaymentMethod
   * @typedef {{ id?: number|string, description: string, quantity: number, unit_type: string, unit_price: string|number }} InvoiceItemDraft
   */

  let invoice = $state(/** @type {import('$lib/types').Invoice|null} */ (null));
  let profile = $state(/** @type {import('$lib/types').BusinessProfile|null} */ (null));
  let loading = $state(true);
  let saving = $state(false);
  let showDiscardModal = $state(false);

  let issueDate = $state('');
  let dueDate = $state('');
  let paymentTermsDays = $state(30);
  let notes = $state('');
  let status = $state('draft');
  let documentType = $state('invoice');
  let clientReference = $state('');
  let showPaymentInstructions = $state(true);
  /** @type {string[]} */
  let selectedPaymentMethods = $state([]);
  /** @type {InvoiceItemDraft[]} */
  let items = $state([]);

  let useDefaultNotes = $state(false);
  let originalNotes = $state('');
  let defaultNotesInitialized = $state(false);

  let taxEnabled = $state(false);
  let taxRate = $state('');
  let taxName = $state('Tax');

  function formState() {
    return JSON.stringify({
      issueDate,
      dueDate,
      paymentTermsDays,
      notes,
      useDefaultNotes,
      status,
      documentType,
      clientReference,
      showPaymentInstructions,
      selectedPaymentMethods,
      items,
      taxEnabled,
      taxRate,
      taxName,
    });
  }

  const guard = createUnsavedGuard(formState);

  // Issue date and terms as last loaded or recomputed, so loading a saved invoice
  // never overwrites its stored due date.
  let dueDateBasis = '';
  $effect(() => {
    const basis = `${issueDate}|${paymentTermsDays}`;
    if (basis === dueDateBasis) return;
    dueDateBasis = basis;
    if (issueDate && paymentTermsDays != null && `${paymentTermsDays}` !== '') {
      dueDate = addDays(issueDate, Number(paymentTermsDays));
    }
  });

  let defaultNotesText = $derived(profile?.default_notes || '');

  onMount(async () => {
    await Promise.all([loadInvoice(), loadProfile()]);
    // After the effect below flips useDefaultNotes, or the baseline is dirty from the start.
    await tick();
    guard.snapshot();
  });

  async function loadProfile() {
    try {
      profile = await profileApi.get();
    } catch (error) {
      console.error('Failed to load profile');
    }
  }

  /** @type {PaymentMethod[]} */
  let availablePaymentMethods = $derived(parseJsonArray(profile?.payment_methods));

  async function loadInvoice() {
    loading = true;
    try {
      const data = await invoicesApi.get(invoiceId);
      invoice = data;

      issueDate = data.issue_date || '';
      dueDate = data.due_date || '';
      paymentTermsDays = data.payment_terms_days ?? 30;
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

      taxEnabled = data.tax_enabled || false;
      taxRate = data.tax_rate && parseFloat(data.tax_rate) > 0 ? data.tax_rate : '';
      taxName = data.tax_name || 'Tax';

      originalNotes = data.notes || '';
      dueDateBasis = `${issueDate}|${paymentTermsDays}`;
    } catch (error) {
      toast.error(error.message || 'Failed to load invoice');
      guard.allowLeave();
      goto('/invoices');
    } finally {
      loading = false;
    }
  }

  let effectiveNotes = $derived(useDefaultNotes && defaultNotesText ? defaultNotesText : notes);
  run(() => {
    if (!defaultNotesInitialized && profile && invoice) {
      useDefaultNotes = !!(profile.default_notes && originalNotes === profile.default_notes);
      defaultNotesInitialized = true;
    }
  });

  async function saveInvoice() {
    const validItems = items.filter(item => item.description.trim() && Number.isFinite(parseFloat(String(item.unit_price))));
    if (validItems.length === 0) {
      toast.error('Please add at least one line item');
      return;
    }

    saving = true;
    try {
      await invoicesApi.update(invoiceId, {
        issue_date: issueDate || undefined,
        due_date: dueDate || undefined,
        // An emptied number input binds null; 0 is a real value (due on receipt).
        payment_terms_days: paymentTermsDays == null ? undefined : Number(paymentTermsDays),
        notes: effectiveNotes,
        // Paid is applied last so its payment covers the new total. Any other change
        // goes first: the item calls can already move a paid invoice back to sent, after
        // which a later status update no longer removes the "Marked paid" payment.
        status: status !== invoice?.status && status !== 'paid' ? status : undefined,
        document_type: documentType,
        client_reference: clientReference,
        show_payment_instructions: showPaymentInstructions,
        selected_payment_methods: stringifyJsonArray(selectedPaymentMethods),
        tax_enabled: taxEnabled ? 1 : 0,
        tax_rate: taxEnabled && taxRate ? parseFloat(taxRate) : 0,
        tax_name: taxName || 'Tax',
      });

      const originalItemIds = new Set((invoice?.items || []).map((item) => item.id));
      const currentItemIds = new Set(items.filter((item) => item.id).map((item) => item.id));

      for (const itemId of originalItemIds) {
        if (!currentItemIds.has(itemId)) {
          await invoicesApi.deleteItem(invoiceId, itemId);
        }
      }

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

      if (status === 'paid' && invoice?.status !== 'paid') {
        await invoicesApi.update(invoiceId, { status });
      }

      toast.success('Invoice updated successfully');
      guard.allowLeave();
      goto(`/invoices/${invoiceId}`);
    } catch (error) {
      // The save is a sequence of calls; on failure some may have applied.
      // Reload from the server so the form reflects the true persisted state.
      toast.error(
        (error.message || 'Failed to update invoice') +
          ' — reloading the latest saved state.'
      );
      await loadInvoice();
      guard.snapshot();
    } finally {
      saving = false;
    }
  }

  function cancel() {
    showDiscardModal = true;
  }

  function confirmDiscard() {
    showDiscardModal = false;
    guard.allowLeave();
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
    <form onsubmit={preventDefault(saveInvoice)} class="form-layout">
      <InvoiceTypeCard
        bind:documentType
        helpText="Changing document type will not regenerate the number. Create a new document if you need a different number format."
      />

      <InvoiceEditDetailsCard
        {invoice}
        {documentType}
        bind:issueDate
        bind:dueDate
        bind:paymentTermsDays
        bind:status
        bind:clientReference
      />

      <InvoiceLineItemsCard
        bind:items
        {taxEnabled}
        {taxRate}
        {taxName}
        currencyCode={invoice?.currency_code || 'USD'}
      />

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

      <div class="form-actions">
        <button
          type="button"
          class="btn btn-secondary"
          onclick={cancel}
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
