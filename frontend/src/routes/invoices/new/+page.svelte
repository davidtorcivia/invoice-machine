<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { clientsApi, invoicesApi, profileApi } from '$lib/api';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import { toast } from '$lib/stores';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
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
  let clients = [];
  let profile = null;
  let loading = false;
  let saving = false;

  // Form data
  let clientId = '';
  let issueDate = new Date().toISOString().split('T')[0];
  let paymentTermsDays = 30;
  let currencyCode = 'USD';
  let notes = '';
  let useDefaultNotes = true;
  let isQuote = false;
  let clientReference = '';
  let showPaymentInstructions = true;
  let invoiceNumberOverride = '';
  /** @type {string[]} */
  let selectedPaymentMethods = [];

  // Tax settings
  let taxEnabled = false;
  let taxRate = '';
  let taxName = 'Tax';

  // Line items
  /** @type {InvoiceItemDraft[]} */
  let items = [{ description: '', quantity: 1, unit_price: '', unit_type: 'qty' }];

  // Modal states
  let showClientModal = false;
  let clientModalSaving = false;
  let showDiscardModal = false;

  /** @type {NewClientDraft} */
  let newClient = {
    name: '',
    business_name: '',
    email: '',
    phone: '',
    address_line1: '',
    city: '',
    state: '',
    postal_code: '',
    payment_terms_days: 30,
  };

  onMount(async () => {
    await Promise.all([loadClients(), loadProfile()]);
  });

  async function loadClients() {
    loading = true;
    try {
      clients = await clientsApi.list();
    } catch (error) {
      toast.error('Failed to load clients');
    } finally {
      loading = false;
    }
  }

  async function loadProfile() {
    try {
      profile = await profileApi.get();
      // Set defaults from profile
      if (profile.default_payment_terms_days) {
        paymentTermsDays = profile.default_payment_terms_days;
      }
      // Set default currency from profile
      if (profile.default_currency_code) {
        currencyCode = profile.default_currency_code;
      }
      // Set tax defaults from profile
      if (profile.default_tax_enabled) {
        taxEnabled = true;
      }
      if (profile.default_tax_rate) {
        taxRate = profile.default_tax_rate;
      }
      if (profile.default_tax_name) {
        taxName = profile.default_tax_name;
      }
    } catch (error) {
      console.error('Failed to load profile');
    }
  }

  // Computed values
  $: defaultNotesText = profile?.default_notes || '';
  $: effectiveNotes = useDefaultNotes && defaultNotesText ? defaultNotesText : notes;

  // Get selected client data
  $: selectedClient = clients.find(c => c.id === parseInt(clientId)) || null;

  // When client changes, update currency and tax settings from client
  $: if (selectedClient) {
    // Use client's preferred currency if set
    if (selectedClient.preferred_currency) {
      currencyCode = selectedClient.preferred_currency;
    }
    // Use client's payment terms if set
    if (selectedClient.payment_terms_days) {
      paymentTermsDays = selectedClient.payment_terms_days;
    }
    // Use client's tax settings if they have custom settings (tax_enabled is not null)
    if (selectedClient.tax_enabled !== null) {
      taxEnabled = !!selectedClient.tax_enabled;
      if (selectedClient.tax_rate) {
        taxRate = String(selectedClient.tax_rate);
      }
      if (selectedClient.tax_name) {
        taxName = selectedClient.tax_name;
      }
    }
  }

  // Parse payment methods from profile
  /** @type {PaymentMethod[]} */
  $: availablePaymentMethods = parseJsonArray(profile?.payment_methods);

  function handleClientModalKeydown(event) {
    if (event.key === 'Escape') {
      closeClientModal();
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
        // Tax settings
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

      // Add invoice number override if provided
      if (invoiceNumberOverride.trim()) {
        invoiceData.invoice_number_override = invoiceNumberOverride.trim();
      }

      const invoice = await invoicesApi.create(invoiceData);

      toast.success(isQuote ? 'Quote created successfully' : 'Invoice created successfully');
      goto(`/invoices/${invoice.id}`);
    } catch (error) {
      toast.error(error.message || 'Failed to create invoice');
    } finally {
      saving = false;
    }
  }

  function openClientModal() {
    newClient = {
      name: '',
      business_name: '',
      email: '',
      phone: '',
      address_line1: '',
      city: '',
      state: '',
      postal_code: '',
      payment_terms_days: 30,
    };
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
      const client = await clientsApi.create({
        name: newClient.name || undefined,
        business_name: newClient.business_name || undefined,
        email: newClient.email || undefined,
        phone: newClient.phone || undefined,
        address_line1: newClient.address_line1 || undefined,
        city: newClient.city || undefined,
        state: newClient.state || undefined,
        postal_code: newClient.postal_code || undefined,
        payment_terms_days: Number(newClient.payment_terms_days) || undefined,
      });

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
    goto('/invoices');
  }
</script>

<Header title={isQuote ? "New Quote" : "New Invoice"} subtitle={isQuote ? "Create a new quote" : "Create a new invoice"} />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <form on:submit|preventDefault={saveInvoice} class="form-layout">
      <!-- Document Type -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Document Type</h3>
        </div>
        <label class="checkbox-label">
          <input type="checkbox" bind:checked={isQuote} />
          <span>This is a Quote</span>
        </label>
        <p class="form-hint">Quotes use a different number format (Q-YYYYMMDD-N) and show "Quote" instead of "Invoice" on the PDF.</p>
      </div>

      <!-- Client & Dates -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Client & Dates</h3>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="client" class="label">Client *</label>
            <div class="client-select-wrapper">
              <select id="client" class="select" bind:value={clientId} required>
                <option value="">Select a client...</option>
                {#each clients as client}
                  <option value={client.id}>{client.business_name || client.name}</option>
                {/each}
              </select>
              <button
                type="button"
                class="btn btn-secondary btn-sm new-client-btn"
                on:click={openClientModal}
              >
                <Icon name="plus" size="sm" />
                New
              </button>
            </div>
          </div>

          <div class="form-group">
            <label for="issue-date" class="label">Issue Date</label>
            <input
              id="issue-date"
              type="date"
              class="input"
              bind:value={issueDate}
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="terms" class="label">Payment Terms (days)</label>
            <input
              id="terms"
              type="number"
              class="input"
              min="0"
              bind:value={paymentTermsDays}
            />
          </div>

          <div class="form-group">
            <label for="currency" class="label">Currency</label>
            <select id="currency" class="select" bind:value={currencyCode}>
              {#each currencies as currency}
                {#if currency.disabled}
                  <option value="" disabled>{currency.name}</option>
                {:else}
                  <option value={currency.code}>{currency.code} - {currency.name}</option>
                {/if}
              {/each}
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="client-ref" class="label">Client Reference / PO Number</label>
            <input
              id="client-ref"
              type="text"
              class="input"
              placeholder="PO-12345"
              bind:value={clientReference}
            />
          </div>

          <div class="form-group">
            <label for="invoice-number" class="label">{isQuote ? 'Quote' : 'Invoice'} Number Override</label>
            <input
              id="invoice-number"
              type="text"
              class="input"
              placeholder="Auto-generated"
              bind:value={invoiceNumberOverride}
            />
            <p class="form-hint">Leave blank for automatic numbering.</p>
          </div>
        </div>

      </div>

      <InvoiceLineItemsCard bind:items bind:taxEnabled bind:taxRate bind:taxName />

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
          {saving ? 'Creating...' : (isQuote ? 'Create Quote' : 'Create Invoice')}
        </button>
      </div>
    </form>
  {/if}
</div>

<!-- Discard Changes Modal -->
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

<!-- New Client Modal -->
{#if showClientModal}
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={handleClientModalKeydown}>
    <button type="button" class="modal-backdrop" aria-label="Close create client dialog" on:click={closeClientModal}></button>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1">
      <div class="modal-header">
        <h2 id="modal-title" class="modal-title">New Client</h2>
        <button class="btn btn-ghost btn-icon btn-sm" on:click={closeClientModal}>
          <Icon name="x" size="md" />
        </button>
      </div>

      <div class="modal-body">
        <div class="form-row">
          <div class="form-group">
            <label for="client-name" class="label">Contact Name</label>
            <input
              id="client-name"
              type="text"
              class="input"
              placeholder="John Smith"
              bind:value={newClient.name}
            />
          </div>

          <div class="form-group">
            <label for="client-business" class="label">Business Name</label>
            <input
              id="client-business"
              type="text"
              class="input"
              placeholder="Acme Inc."
              bind:value={newClient.business_name}
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="client-email" class="label">Email</label>
            <input
              id="client-email"
              type="email"
              class="input"
              placeholder="john@example.com"
              bind:value={newClient.email}
            />
          </div>

          <div class="form-group">
            <label for="client-phone" class="label">Phone</label>
            <input
              id="client-phone"
              type="tel"
              class="input"
              placeholder="(555) 123-4567"
              bind:value={newClient.phone}
            />
          </div>
        </div>

        <div class="form-group">
          <label for="client-address" class="label">Street Address</label>
          <input
            id="client-address"
            type="text"
            class="input"
            placeholder="123 Main St"
            bind:value={newClient.address_line1}
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="client-city" class="label">City</label>
            <input
              id="client-city"
              type="text"
              class="input"
              bind:value={newClient.city}
            />
          </div>

          <div class="form-group">
            <label for="client-state" class="label">State</label>
            <input
              id="client-state"
              type="text"
              class="input"
              bind:value={newClient.state}
            />
          </div>

          <div class="form-group">
            <label for="client-postal" class="label">ZIP Code</label>
            <input
              id="client-postal"
              type="text"
              class="input"
              bind:value={newClient.postal_code}
            />
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button
          type="button"
          class="btn btn-secondary"
          on:click={closeClientModal}
          disabled={clientModalSaving}
        >
          Cancel
        </button>
        <button
          type="button"
          class="btn btn-primary"
          on:click={saveNewClient}
          disabled={clientModalSaving}
        >
          {clientModalSaving ? 'Creating...' : 'Create Client'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }

  :global(.modal) {
    position: relative;
  }

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

  .client-select-wrapper {
    display: flex;
    gap: var(--space-2);
  }

  .client-select-wrapper .select {
    flex: 1;
  }

  .new-client-btn {
    flex-shrink: 0;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 500;
  }

  .checkbox-label input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  /* Responsive - Large screens */
  @media (min-width: 1400px) {
    .page-content {
      max-width: 1100px;
    }
  }

  /* Responsive - Medium screens */
  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .client-select-wrapper {
      flex-direction: column;
    }
  }

  /* Responsive - Small screens */
  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .form-row {
      grid-template-columns: 1fr;
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
