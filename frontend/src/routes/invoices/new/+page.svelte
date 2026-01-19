<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { clientsApi, invoicesApi, profileApi } from '$lib/api';
  import { formatCurrency, toast } from '$lib/stores';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

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
  let selectedPaymentMethods = [];

  // Tax settings
  let taxEnabled = false;
  let taxRate = '';
  let taxName = 'Tax';

  // Line items
  let items = [{ description: '', quantity: 1, unit_price: '', unit_type: 'qty' }];

  // Modal states
  let showClientModal = false;
  let clientModalSaving = false;
  let showDiscardModal = false;

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
        taxRate = selectedClient.tax_rate;
      }
      if (selectedClient.tax_name) {
        taxName = selectedClient.tax_name;
      }
    }
  }

  // Parse payment methods from profile
  $: availablePaymentMethods = (() => {
    try {
      return profile?.payment_methods ? JSON.parse(profile.payment_methods) : [];
    } catch {
      return [];
    }
  })();

  function removeDefaultNotes() {
    useDefaultNotes = false;
    notes = '';
  }

  function addItem() {
    items = [...items, { description: '', quantity: 1, unit_price: '', unit_type: 'qty' }];
  }

  function removeItem(index) {
    if (items.length > 1) {
      items = items.filter((_, i) => i !== index);
    }
  }

  $: subtotal = items.reduce((sum, item) => {
    const price = parseFloat(item.unit_price) || 0;
    return sum + (price * item.quantity);
  }, 0);

  $: taxAmount = taxEnabled && taxRate ? (subtotal * parseFloat(taxRate) / 100) : 0;
  $: total = subtotal + taxAmount;

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
        client_id: parseInt(clientId),
        issue_date: issueDate || undefined,
        payment_terms_days: parseInt(paymentTermsDays) || undefined,
        currency_code: currencyCode,
        notes: effectiveNotes || undefined,
        document_type: isQuote ? 'quote' : 'invoice',
        client_reference: clientReference || undefined,
        show_payment_instructions: showPaymentInstructions,
        selected_payment_methods: selectedPaymentMethods.length > 0 ? JSON.stringify(selectedPaymentMethods) : null,
        // Tax settings
        tax_enabled: taxEnabled ? 1 : 0,
        tax_rate: taxEnabled && taxRate ? parseFloat(taxRate) : 0,
        tax_name: taxName || 'Tax',
        items: validItems.map(item => ({
          description: item.description,
          quantity: parseInt(item.quantity) || 1,
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
        payment_terms_days: parseInt(newClient.payment_terms_days) || undefined,
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

      <!-- Line Items -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Line Items</h3>
          <button type="button" class="btn btn-secondary btn-sm" on:click={addItem}>
            <Icon name="plus" size="sm" />
            Add Item
          </button>
        </div>

        <div class="items-list">
          {#each items as item, index}
            <div class="item-row">
              <div class="item-fields">
                <div class="form-group item-desc">
                  <label class="label">Description</label>
                  <input
                    type="text"
                    class="input"
                    placeholder="Service or product description"
                    bind:value={item.description}
                  />
                </div>

                <div class="form-group item-unit-type">
                  <label class="label">Type</label>
                  <select class="select" bind:value={item.unit_type}>
                    <option value="qty">Qty</option>
                    <option value="hours">Hours</option>
                  </select>
                </div>

                <div class="form-group item-qty">
                  <label class="label">{item.unit_type === 'hours' ? 'Hours' : 'Qty'}</label>
                  <input
                    type="number"
                    class="input"
                    min="1"
                    step={item.unit_type === 'hours' ? '0.5' : '1'}
                    bind:value={item.quantity}
                  />
                </div>

                <div class="form-group item-price">
                  <label class="label">{item.unit_type === 'hours' ? 'Rate' : 'Price'}</label>
                  <input
                    type="number"
                    class="input"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    bind:value={item.unit_price}
                  />
                </div>

                <div class="form-group item-total">
                  <label class="label">Total</label>
                  <div class="item-total-value">
                    {formatCurrency((parseFloat(item.unit_price) || 0) * item.quantity)}
                  </div>
                </div>
              </div>

              <button
                type="button"
                class="btn btn-ghost btn-icon btn-sm btn-remove"
                on:click={() => removeItem(index)}
                disabled={items.length === 1}
                title="Remove item"
              >
                <Icon name="x" size="sm" />
              </button>
            </div>
          {/each}
        </div>

        <div class="totals-summary">
          <div class="totals-row">
            <span class="totals-label">Subtotal</span>
            <span class="totals-value">{formatCurrency(subtotal)}</span>
          </div>
          {#if taxEnabled && taxRate}
            <div class="totals-row tax-row">
              <span class="totals-label">{taxName} ({taxRate}%)</span>
              <span class="totals-value">{formatCurrency(taxAmount)}</span>
            </div>
            <div class="totals-row total-row">
              <span class="totals-label">Total</span>
              <span class="totals-value total-value">{formatCurrency(total)}</span>
            </div>
          {/if}
        </div>
      </div>

      <!-- Tax Settings -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Tax Settings</h3>
        </div>

        <label class="checkbox-label">
          <input type="checkbox" bind:checked={taxEnabled} />
          <span>Apply Tax</span>
        </label>

        {#if taxEnabled}
          <div class="form-row tax-fields">
            <div class="form-group">
              <label for="tax-rate" class="label">Tax Rate (%)</label>
              <input
                id="tax-rate"
                type="number"
                class="input"
                step="0.01"
                min="0"
                max="100"
                placeholder="e.g., 8.5"
                bind:value={taxRate}
              />
            </div>

            <div class="form-group">
              <label for="tax-name" class="label">Tax Name</label>
              <input
                id="tax-name"
                type="text"
                class="input"
                placeholder="Tax, VAT, GST, etc."
                bind:value={taxName}
              />
            </div>
          </div>
          <p class="form-hint">Tax will be calculated on the subtotal and shown on the invoice.</p>
        {:else}
          <p class="form-hint">
            Enable tax to add a tax line to this invoice.
            {#if profile?.default_tax_enabled}
              Default tax ({profile.default_tax_rate}%) is configured in Settings.
            {/if}
          </p>
        {/if}
      </div>

      <!-- Payment Methods Selection -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Payment Instructions</h3>
        </div>

        {#if availablePaymentMethods.length > 0}
          <p class="form-hint" style="margin-top: 0; margin-bottom: var(--space-3);">
            Select payment methods to include on the PDF. Clients will see instructions for all selected methods.
          </p>
          <div class="payment-methods-list">
            {#each availablePaymentMethods as method}
              <label class="payment-method-option">
                <input
                  type="checkbox"
                  checked={selectedPaymentMethods.includes(method.id)}
                  on:change={(e) => {
                    if (e.target.checked) {
                      selectedPaymentMethods = [...selectedPaymentMethods, method.id];
                    } else {
                      selectedPaymentMethods = selectedPaymentMethods.filter(id => id !== method.id);
                    }
                  }}
                />
                <div class="payment-method-info">
                  <span class="payment-method-name">{method.name}</span>
                  {#if method.instructions}
                    <span class="payment-method-preview">{method.instructions.substring(0, 50)}{method.instructions.length > 50 ? '...' : ''}</span>
                  {/if}
                </div>
              </label>
            {/each}
          </div>
          {#if selectedPaymentMethods.length > 0}
            <p class="form-hint selected-count">
              {selectedPaymentMethods.length} payment method{selectedPaymentMethods.length !== 1 ? 's' : ''} will be shown on the PDF.
            </p>
          {/if}
        {:else}
          <label class="checkbox-label">
            <input type="checkbox" bind:checked={showPaymentInstructions} />
            <span>Include Payment Instructions</span>
          </label>
          <p class="form-hint">
            Configure payment methods in <a href="/settings" class="link">Settings</a> to select which ones to show on invoices.
          </p>
        {/if}
      </div>

      <!-- Notes -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Notes</h3>
        </div>

        {#if useDefaultNotes && defaultNotesText}
          <div class="default-notes-display">
            <div class="default-notes-header">
              <span class="default-notes-label">Using default notes from Settings</span>
              <button
                type="button"
                class="btn btn-ghost btn-sm"
                on:click={removeDefaultNotes}
              >
                <Icon name="x" size="sm" />
                Remove
              </button>
            </div>
            <div class="default-notes-content">
              {defaultNotesText}
            </div>
          </div>
        {:else}
          <textarea
            class="textarea"
            rows="3"
            placeholder="Payment terms, thank you message, etc."
            bind:value={notes}
          ></textarea>
          {#if defaultNotesText && !useDefaultNotes}
            <button
              type="button"
              class="btn btn-ghost btn-sm mt-2"
              on:click={() => { useDefaultNotes = true; notes = ''; }}
            >
              <Icon name="refresh" size="sm" />
              Use default notes
            </button>
          {/if}
        {/if}
      </div>

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
  <div class="modal-overlay" on:click={closeClientModal} on:keydown={(e) => e.key === 'Escape' && closeClientModal()}>
    <div class="modal" on:click|stopPropagation role="dialog" aria-modal="true" aria-labelledby="modal-title">
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

  .items-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .item-row {
    display: flex;
    gap: var(--space-3);
    align-items: flex-start;
  }

  .item-fields {
    display: flex;
    gap: var(--space-3);
    flex: 1;
    flex-wrap: wrap;
  }

  .item-desc {
    flex: 2;
    min-width: 200px;
  }

  .item-unit-type {
    flex: 0 0 90px;
  }

  .item-qty {
    flex: 0 0 90px;
  }

  .item-price {
    flex: 0 0 120px;
  }

  .item-total {
    flex: 0 0 110px;
  }

  .item-total-value {
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    font-weight: 500;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .btn-remove {
    margin-top: 28px;
    color: var(--color-text-tertiary);
  }

  .btn-remove:hover:not(:disabled) {
    color: var(--color-danger);
  }

  .btn-remove:disabled {
    opacity: 0.3;
  }

  .totals-summary {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-2);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
    margin-top: var(--space-4);
  }

  .totals-row {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-6);
    min-width: 280px;
  }

  .totals-label {
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .totals-value {
    font-size: 1rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    min-width: 100px;
    text-align: right;
  }

  .tax-row .totals-label {
    color: var(--color-text-tertiary);
  }

  .tax-row .totals-value {
    font-weight: 500;
  }

  .total-row {
    padding-top: var(--space-2);
    border-top: 1px solid var(--color-border-light);
  }

  .total-value {
    font-size: 1.25rem;
    color: var(--color-primary);
  }

  .tax-fields {
    margin-top: var(--space-4);
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

  /* Default Notes Display */
  .default-notes-display {
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .default-notes-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-hover);
    border-bottom: 1px solid var(--color-border);
  }

  .default-notes-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }

  .default-notes-content {
    padding: var(--space-3) var(--space-4);
    font-size: 0.9375rem;
    color: var(--color-text);
    white-space: pre-wrap;
    line-height: 1.6;
  }

  .mt-2 {
    margin-top: var(--space-2);
  }

  /* Payment Methods Selection */
  .payment-methods-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .payment-method-option {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-3);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .payment-method-option:hover {
    border-color: var(--color-border-emphasis);
    background: var(--color-bg-hover);
  }

  .payment-method-option:has(input:checked) {
    border-color: var(--color-primary);
    background: color-mix(in srgb, var(--color-primary) 5%, var(--color-bg-sunken));
  }

  .payment-method-option input[type="checkbox"] {
    width: 18px;
    height: 18px;
    margin-top: 2px;
    accent-color: var(--color-primary);
    flex-shrink: 0;
  }

  .payment-method-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .payment-method-name {
    font-weight: 500;
    color: var(--color-text);
  }

  .payment-method-preview {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .selected-count {
    margin-top: var(--space-3);
    color: var(--color-primary);
    font-weight: 500;
  }

  .link {
    color: var(--color-primary);
    text-decoration: none;
  }

  .link:hover {
    text-decoration: underline;
  }

  /* Responsive - Large screens */
  @media (min-width: 1400px) {
    .page-content {
      max-width: 1100px;
    }

    .item-desc {
      flex: 3;
      min-width: 300px;
    }

    .item-unit-type {
      flex: 0 0 100px;
    }

    .item-qty {
      flex: 0 0 100px;
    }

    .item-price {
      flex: 0 0 140px;
    }

    .item-total {
      flex: 0 0 130px;
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

    .item-fields {
      flex-direction: column;
    }

    .item-desc,
    .item-unit-type,
    .item-qty,
    .item-price,
    .item-total {
      flex: 1;
      min-width: 100%;
    }

    .btn-remove {
      margin-top: 0;
      align-self: flex-end;
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
