<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { invoicesApi, profileApi } from '$lib/api';
  import { formatCurrency, toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

  $: id = $page.params.id;

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
  let selectedPaymentMethods = [];
  let items = [];

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
  $: availablePaymentMethods = (() => {
    try {
      return profile?.payment_methods ? JSON.parse(profile.payment_methods) : [];
    } catch {
      return [];
    }
  })();

  async function loadInvoice() {
    loading = true;
    try {
      const data = await invoicesApi.get(id);
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
      // Parse selected payment methods from invoice
      try {
        selectedPaymentMethods = data.selected_payment_methods ? JSON.parse(data.selected_payment_methods) : [];
      } catch {
        selectedPaymentMethods = [];
      }
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
    } catch (error) {
      toast.error('Failed to load invoice');
      goto('/invoices');
    } finally {
      loading = false;
    }
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

  async function saveInvoice() {
    const validItems = items.filter(item => item.description.trim() && item.unit_price);
    if (validItems.length === 0) {
      toast.error('Please add at least one line item');
      return;
    }

    saving = true;
    try {
      // Update invoice details
      await invoicesApi.update(id, {
        issue_date: issueDate || undefined,
        due_date: dueDate || undefined,
        payment_terms_days: parseInt(paymentTermsDays) || undefined,
        notes: notes || undefined,
        status: status,
        document_type: documentType,
        client_reference: clientReference || undefined,
        show_payment_instructions: showPaymentInstructions,
        selected_payment_methods: selectedPaymentMethods.length > 0 ? JSON.stringify(selectedPaymentMethods) : null,
      });

      // Delete removed items
      const originalItemIds = new Set((invoice.items || []).map(i => i.id));
      const currentItemIds = new Set(items.filter(i => i.id).map(i => i.id));

      for (const itemId of originalItemIds) {
        if (!currentItemIds.has(itemId)) {
          await invoicesApi.deleteItem(id, itemId);
        }
      }

      // Update existing items and add new ones
      for (let i = 0; i < validItems.length; i++) {
        const item = validItems[i];
        if (item.id) {
          await invoicesApi.updateItem(id, item.id, {
            description: item.description,
            quantity: parseInt(item.quantity) || 1,
            unit_type: item.unit_type || 'qty',
            unit_price: parseFloat(item.unit_price) || 0,
            sort_order: i,
          });
        } else {
          await invoicesApi.addItem(id, {
            description: item.description,
            quantity: parseInt(item.quantity) || 1,
            unit_type: item.unit_type || 'qty',
            unit_price: parseFloat(item.unit_price) || 0,
            sort_order: i,
          });
        }
      }

      toast.success('Invoice updated successfully');
      goto(`/invoices/${id}`);
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
    goto(`/invoices/${id}`);
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
      <!-- Document Type -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Document Type</h3>
        </div>
        <label class="checkbox-label">
          <input type="checkbox" checked={documentType === 'quote'} on:change={(e) => documentType = e.target.checked ? 'quote' : 'invoice'} />
          <span>This is a Quote</span>
        </label>
        <p class="form-hint">Changing document type will not regenerate the number. Create a new document if you need a different number format.</p>
      </div>

      <!-- Invoice Details -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{documentType === 'quote' ? 'Quote' : 'Invoice'} Details</h3>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="issue-date" class="label">Issue Date</label>
            <input
              id="issue-date"
              type="date"
              class="input"
              bind:value={issueDate}
            />
            <p class="form-hint">Changing the issue date may update the invoice number.</p>
          </div>

          <div class="form-group">
            <label for="due-date" class="label">Due Date</label>
            <input
              id="due-date"
              type="date"
              class="input"
              bind:value={dueDate}
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
            <label for="status" class="label">Status</label>
            <select id="status" class="select" bind:value={status}>
              <option value="draft">Draft</option>
              <option value="sent">Sent</option>
              <option value="paid">Paid</option>
              <option value="overdue">Overdue</option>
              <option value="cancelled">Cancelled</option>
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
          <span class="totals-label">Subtotal</span>
          <span class="totals-value">{formatCurrency(subtotal)}</span>
        </div>
      </div>

      <!-- Payment Methods Selection -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Payment Instructions</h3>
        </div>

        {#if availablePaymentMethods.length > 0}
          <p class="form-hint" style="margin-top: 0; margin-bottom: var(--space-3);">
            Select payment methods to include on the PDF.
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
        <textarea
          class="textarea"
          rows="3"
          placeholder="Payment terms, thank you message, etc."
          bind:value={notes}
        ></textarea>
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

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
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
    flex: 0 0 80px;
  }

  .item-qty {
    flex: 0 0 80px;
  }

  .item-price {
    flex: 0 0 120px;
  }

  .item-total {
    flex: 0 0 100px;
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
    justify-content: flex-end;
    gap: var(--space-6);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
    margin-top: var(--space-4);
  }

  .totals-label {
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .totals-value {
    font-size: 1.125rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
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
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
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

    .form-actions {
      flex-direction: column-reverse;
    }

    .form-actions .btn {
      width: 100%;
    }
  }
</style>
