<script>
  import { run, preventDefault } from 'svelte/legacy';

  import { onMount } from 'svelte';
  import { goto, beforeNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { clientsApi, invoicesApi, profileApi } from '$lib/api';
  import { buildClientPayload, createClientDraft } from '$lib/clients/config';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import ClientQuickCreateModal from '$lib/components/clients/ClientQuickCreateModal.svelte';
  import InvoiceClientDetailsCard from '$lib/components/invoices/InvoiceClientDetailsCard.svelte';
  import InvoiceDocumentTypeCard from '$lib/components/invoices/InvoiceDocumentTypeCard.svelte';
  import InvoiceLineItemsCard from '$lib/components/invoices/InvoiceLineItemsCard.svelte';
  import InvoiceNotesCard from '$lib/components/invoices/InvoiceNotesCard.svelte';
  import InvoicePaymentInstructionsCard from '$lib/components/invoices/InvoicePaymentInstructionsCard.svelte';
  import InvoiceTaxCard from '$lib/components/invoices/InvoiceTaxCard.svelte';

  /**
   * @typedef {{ id: string, name: string, instructions?: string }} PaymentMethod
   * @typedef {{ id: number|string, name?: string, business_name?: string, preferred_currency?: string, payment_terms_days?: number, tax_enabled?: boolean | null, tax_rate?: string|number, tax_name?: string }} ClientSummary
   * @typedef {{ description: string, quantity: number, unit_price: string, unit_type: string }} InvoiceItemDraft
   * @typedef {{ name: string, business_name: string, email: string, phone: string, address_line1: string, city: string, state: string, postal_code: string, payment_terms_days: string | number }} NewClientDraft
   */

  /** @type {ClientSummary[]} */
  let clients = $state([]);
  let profile = $state(/** @type {import('$lib/types').BusinessProfile|null} */ (null));
  let loading = $state(false);
  let saving = $state(false);
  let allowLeave = $state(false);

  let clientId = $state('');
  let issueDate = $state(new Date().toISOString().split('T')[0]);
  let paymentTermsDays = $state(30);
  let currencyCode = $state('USD');
  let notes = $state('');
  let useDefaultNotes = $state(true);
  let isQuote = $state(false);
  let clientReference = $state('');
  let showPaymentInstructions = $state(true);
  let invoiceNumberOverride = $state('');
  /** @type {string[]} */
  let selectedPaymentMethods = $state([]);

  let taxEnabled = $state(false);
  let taxRate = $state('');
  let taxName = $state('Tax');

  /** @type {InvoiceItemDraft[]} */
  let items = $state([{ description: '', quantity: 1, unit_price: '', unit_type: 'qty' }]);

  // Warn before navigating away from a partially-filled form: any client chosen
  // or line item started counts as work worth keeping.
  let isDirty = $derived(
    !allowLeave &&
    (!!clientId ||
      !!(notes && notes.trim()) ||
      items.some((i) => (i.description || '').trim() || `${i.unit_price ?? ''}`.trim())));

  beforeNavigate((nav) => {
    if (isDirty && !saving) {
      if (!confirm('You have unsaved changes. Leave without saving?')) {
        nav.cancel();
      }
    }
  });

  let showClientModal = $state(false);
  let clientModalSaving = $state(false);
  let showDiscardModal = $state(false);

  /** @type {NewClientDraft} */
  let newClient = $state({
    name: '',
    business_name: '',
    email: '',
    phone: '',
    address_line1: '',
    city: '',
    state: '',
    postal_code: '',
    payment_terms_days: 30,
  });

  onMount(async () => {
    await Promise.all([loadClients(), loadProfile()]);
  });

  async function loadClients() {
    loading = true;
    try {
      clients = await clientsApi.list();
      // Preselect a client when arriving from a client page (?client=<id>).
      const requested = $page.url.searchParams.get('client');
      if (requested && clients.some((c) => c.id === parseInt(requested))) {
        clientId = requested;
      }
    } catch (error) {
      toast.error('Failed to load clients');
    } finally {
      loading = false;
    }
  }

  async function loadProfile() {
    try {
      const loaded = await profileApi.get();
      profile = loaded;

      // Seed the form from the business defaults.
      if (loaded.default_payment_terms_days) paymentTermsDays = loaded.default_payment_terms_days;
      if (loaded.default_currency_code) currencyCode = loaded.default_currency_code;
      if (loaded.default_tax_enabled) taxEnabled = true;
      if (loaded.default_tax_rate) taxRate = loaded.default_tax_rate;
      if (loaded.default_tax_name) taxName = loaded.default_tax_name;
    } catch (error) {
      console.error('Failed to load profile');
    }
  }

  // Apply client defaults ONLY when the selected client actually changes, so a
  // background clients refresh (or any other reactive recompute) can't clobber
  // values the user has since edited by hand.
  let appliedClientId = null;

  function applyClientDefaults(client) {
    if (!client) {
      appliedClientId = null;
      return;
    }
    if (client.id === appliedClientId) return;
    appliedClientId = client.id;

    if (client.preferred_currency) {
      currencyCode = client.preferred_currency;
    }
    if (client.payment_terms_days) {
      paymentTermsDays = client.payment_terms_days;
    }
    // Apply client tax settings only if the client has explicit overrides.
    if (client.tax_enabled !== null && client.tax_enabled !== undefined) {
      taxEnabled = !!client.tax_enabled;
      if (client.tax_rate) {
        taxRate = String(client.tax_rate);
      }
      if (client.tax_name) {
        taxName = client.tax_name;
      }
    }
  }


  async function saveInvoice() {
    if (!clientId) {
      toast.error('Please select a client');
      return;
    }

    const validItems = items.filter(item => item.description.trim() && item.unit_price);
    if (validItems.length === 0) {
      toast.error('Please add at least one line item with a description and price');
      return;
    }

    saving = true;
    try {
      const invoiceData = {
        client_id: Number(clientId),
        issue_date: issueDate || undefined,
        payment_terms_days: Number(paymentTermsDays) || undefined,
        currency_code: currencyCode,
        notes: effectiveNotes || undefined,
        document_type: isQuote ? 'quote' : 'invoice',
        client_reference: clientReference || undefined,
        show_payment_instructions: showPaymentInstructions,
        selected_payment_methods: stringifyJsonArray(selectedPaymentMethods),
        tax_enabled: taxEnabled ? 1 : 0,
        tax_rate: taxEnabled && taxRate ? parseFloat(taxRate) : 0,
        tax_name: taxName || 'Tax',
        items: validItems.map(item => ({
          description: item.description,
          quantity: Number(item.quantity) || 1,
          unit_type: item.unit_type || 'qty',
          unit_price: parseFloat(item.unit_price) || 0,
        })),
      };

      if (invoiceNumberOverride.trim()) {
        invoiceData.invoice_number_override = invoiceNumberOverride.trim();
      }

      const invoice = await invoicesApi.create(invoiceData);

      toast.success(isQuote ? 'Quote created successfully' : 'Invoice created successfully');
      allowLeave = true;
      goto(`/invoices/${invoice.id}`);
    } catch (error) {
      toast.error(error.message || 'Failed to create invoice');
    } finally {
      saving = false;
    }
  }

  function openClientModal() {
    newClient = createClientDraft();
    showClientModal = true;
  }

  function closeClientModal() {
    showClientModal = false;
  }

  async function saveNewClient() {
    if (!newClient.name && !newClient.business_name) {
      toast.error('Please enter a name or business name');
      return;
    }

    clientModalSaving = true;
    try {
      const client = await clientsApi.create(buildClientPayload(newClient));

      toast.success('Client created successfully');
      await loadClients();
      clientId = client.id.toString();
      closeClientModal();
    } catch (error) {
      toast.error('Failed to create client');
    } finally {
      clientModalSaving = false;
    }
  }

  function cancel() {
    showDiscardModal = true;
  }

  function confirmDiscard() {
    showDiscardModal = false;
    allowLeave = true;
    goto('/invoices');
  }

  let defaultNotesText = $derived(profile?.default_notes || '');
  let effectiveNotes = $derived(useDefaultNotes && defaultNotesText ? defaultNotesText : notes);
  let selectedClient = $derived(clients.find(c => c.id === parseInt(clientId)) || null);
  run(() => {
    applyClientDefaults(selectedClient);
  });

  /** @type {PaymentMethod[]} */
  let availablePaymentMethods = $derived(parseJsonArray(profile?.payment_methods));
</script>

<Header title={isQuote ? "New Quote" : "New Invoice"} subtitle={isQuote ? "Create a new quote" : "Create a new invoice"} />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <form onsubmit={preventDefault(saveInvoice)} class="form-layout">
      <InvoiceDocumentTypeCard bind:isQuote />

      <InvoiceClientDetailsCard
        {clients}
        bind:clientId
        bind:issueDate
        bind:paymentTermsDays
        bind:currencyCode
        bind:clientReference
        bind:invoiceNumberOverride
        {isQuote}
        {openClientModal}
      />

      <InvoiceLineItemsCard bind:items {taxEnabled} {taxRate} {taxName} {currencyCode} />

      <InvoiceTaxCard
        bind:taxEnabled
        bind:taxRate
        bind:taxName
        checkboxLabel="Apply Tax"
        enabledHint="Tax will be calculated on the subtotal and shown on the invoice."
        disabledHint={profile?.default_tax_enabled
          ? `Enable tax to add a tax line to this invoice. Default tax (${profile.default_tax_rate}%) is configured in Settings.`
          : 'Enable tax to add a tax line to this invoice.'}
      />

      <InvoicePaymentInstructionsCard
        {availablePaymentMethods}
        bind:selectedPaymentMethods
        bind:showPaymentInstructions
        selectionHint="Select payment methods to include on the PDF. Clients will see instructions for all selected methods."
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
          {saving ? 'Creating...' : (isQuote ? 'Create Quote' : 'Create Invoice')}
        </button>
      </div>
    </form>
  {/if}
</div>

<ConfirmModal
  show={showDiscardModal}
  title="Discard Changes?"
  message="Are you sure you want to discard your changes and return to invoices?"
  confirmText="Discard"
  icon="warning"
  variant="warning"
  onConfirm={confirmDiscard}
  onCancel={() => showDiscardModal = false}
/>

<ClientQuickCreateModal show={showClientModal} saving={clientModalSaving} draft={newClient} close={closeClientModal} save={saveNewClient} />

<style>
  .page-content {
    padding: var(--space-6) var(--space-8);
    max-width: 1000px;
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
      min-height: 44px;
    }
  }
</style>
