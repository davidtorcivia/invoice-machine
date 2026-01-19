<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { clientsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import { countries } from '$lib/data/countries';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

  $: id = $page.params.id;

  let client = null;
  let loading = true;
  let saving = false;
  let showDiscardModal = false;

  // Form data
  let name = '';
  let businessName = '';
  let email = '';
  let phone = '';
  let addressLine1 = '';
  let addressLine2 = '';
  let city = '';
  let state = '';
  let postalCode = '';
  let country = '';
  let paymentTermsDays = 30;
  let notes = '';

  // Tax settings
  let taxOverride = false;  // Whether to override global settings
  let taxEnabled = false;
  let taxRate = '';
  let taxName = 'Tax';

  // Currency preference
  let preferredCurrency = '';

  onMount(async () => {
    await loadClient();
  });

  async function loadClient() {
    loading = true;
    try {
      const data = await clientsApi.get(id);
      client = data;

      // Populate form
      name = data.name || '';
      businessName = data.business_name || '';
      email = data.email || '';
      phone = data.phone || '';
      addressLine1 = data.address_line1 || '';
      addressLine2 = data.address_line2 || '';
      city = data.city || '';
      state = data.state || '';
      postalCode = data.postal_code || '';
      country = data.country || '';
      paymentTermsDays = data.payment_terms_days || 30;
      notes = data.notes || '';
      preferredCurrency = data.preferred_currency || '';

      // Load tax settings (null = use global default)
      if (data.tax_enabled !== null) {
        taxOverride = true;
        taxEnabled = !!data.tax_enabled;
        taxRate = data.tax_rate && parseFloat(data.tax_rate) > 0 ? data.tax_rate : '';
        taxName = data.tax_name || 'Tax';
      } else {
        taxOverride = false;
        taxEnabled = false;
        taxRate = '';
        taxName = 'Tax';
      }
    } catch (error) {
      toast.error('Failed to load client');
      goto('/clients');
    } finally {
      loading = false;
    }
  }

  async function saveClient() {
    if (!name.trim() && !businessName.trim()) {
      toast.error('Please enter a contact name or business name');
      return;
    }

    saving = true;
    try {
      // Build update payload
      const updateData = {
        name: name || undefined,
        business_name: businessName || undefined,
        email: email || undefined,
        phone: phone || undefined,
        address_line1: addressLine1 || undefined,
        address_line2: addressLine2 || undefined,
        city: city || undefined,
        state: state || undefined,
        postal_code: postalCode || undefined,
        country: country || undefined,
        payment_terms_days: parseInt(paymentTermsDays) || undefined,
        notes: notes || undefined,
        preferred_currency: preferredCurrency || null,
      };

      // Add tax settings if overriding global defaults
      if (taxOverride) {
        updateData.tax_enabled = taxEnabled ? 1 : 0;
        updateData.tax_rate = taxEnabled && taxRate ? parseFloat(taxRate) : 0;
        updateData.tax_name = taxName || 'Tax';
      } else {
        // null means use global default
        updateData.tax_enabled = null;
        updateData.tax_rate = null;
        updateData.tax_name = null;
      }

      await clientsApi.update(id, updateData);

      toast.success('Client updated successfully');
      goto(`/clients/${id}`);
    } catch (error) {
      toast.error('Failed to update client');
    } finally {
      saving = false;
    }
  }

  function cancel() {
    showDiscardModal = true;
  }

  function confirmDiscard() {
    showDiscardModal = false;
    goto(`/clients/${id}`);
  }
</script>

<Header
  title={client ? `Edit ${client.business_name || client.name}` : 'Edit Client'}
  subtitle="Update client information"
/>

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <form on:submit|preventDefault={saveClient} class="form-layout">
      <!-- Client Information -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Client Information</h3>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="business-name" class="label">Business Name</label>
            <input
              id="business-name"
              type="text"
              class="input"
              placeholder="Company name"
              bind:value={businessName}
            />
          </div>

          <div class="form-group">
            <label for="name" class="label">Contact Name</label>
            <input
              id="name"
              type="text"
              class="input"
              placeholder="Primary contact"
              bind:value={name}
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="email" class="label">Email</label>
            <input
              id="email"
              type="email"
              class="input"
              placeholder="contact@example.com"
              bind:value={email}
            />
          </div>

          <div class="form-group">
            <label for="phone" class="label">Phone</label>
            <input
              id="phone"
              type="tel"
              class="input"
              placeholder="(555) 123-4567"
              bind:value={phone}
            />
          </div>
        </div>
      </div>

      <!-- Address -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Address</h3>
        </div>

        <div class="form-group">
          <label for="address1" class="label">Street Address</label>
          <input
            id="address1"
            type="text"
            class="input"
            placeholder="123 Main St"
            bind:value={addressLine1}
          />
        </div>

        <div class="form-group">
          <label for="address2" class="label">Apartment, suite, etc.</label>
          <input
            id="address2"
            type="text"
            class="input"
            placeholder="Apt 4"
            bind:value={addressLine2}
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="city" class="label">City</label>
            <input
              id="city"
              type="text"
              class="input"
              placeholder="City"
              bind:value={city}
            />
          </div>

          <div class="form-group">
            <label for="state" class="label">State</label>
            <input
              id="state"
              type="text"
              class="input"
              placeholder="State"
              bind:value={state}
            />
          </div>

          <div class="form-group">
            <label for="postal" class="label">ZIP Code</label>
            <input
              id="postal"
              type="text"
              class="input"
              placeholder="12345"
              bind:value={postalCode}
            />
          </div>
        </div>

        <div class="form-group">
          <label for="country" class="label">Country</label>
          <select id="country" class="select" bind:value={country}>
            <option value="">Select a country...</option>
            {#each countries as c}
              <option value={c}>{c}</option>
            {/each}
          </select>
        </div>
      </div>

      <!-- Settings -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Settings</h3>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="terms" class="label">Default Payment Terms (days)</label>
            <input
              id="terms"
              type="number"
              class="input"
              min="0"
              bind:value={paymentTermsDays}
            />
            <p class="form-hint">Used as the default when creating new invoices for this client.</p>
          </div>

          <div class="form-group">
            <label for="currency" class="label">Preferred Currency</label>
            <select id="currency" class="select" bind:value={preferredCurrency}>
              <option value="">Use default (from Settings)</option>
              {#each currencies as c}
                {#if c.disabled}
                  <option value="" disabled>{c.name}</option>
                {:else}
                  <option value={c.code}>{c.code} - {c.name}</option>
                {/if}
              {/each}
            </select>
            <p class="form-hint">Pre-select this currency when creating invoices for this client.</p>
          </div>
        </div>

        <div class="form-group">
          <label for="notes" class="label">Notes</label>
          <textarea
            id="notes"
            class="textarea"
            rows="3"
            placeholder="Internal notes about this client..."
            bind:value={notes}
          ></textarea>
        </div>
      </div>

      <!-- Tax Settings -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Tax Settings</h3>
        </div>

        <label class="checkbox-label">
          <input type="checkbox" bind:checked={taxOverride} />
          <span>Override global tax settings for this client</span>
        </label>
        <p class="form-hint">When unchecked, invoices for this client will use your global default tax settings.</p>

        {#if taxOverride}
          <div class="tax-override-section">
            <label class="checkbox-label">
              <input type="checkbox" bind:checked={taxEnabled} />
              <span>Enable Tax</span>
            </label>

            {#if taxEnabled}
              <div class="form-row" style="margin-top: var(--space-4);">
                <div class="form-group">
                  <label for="tax-rate" class="label">Tax Rate (%)</label>
                  <input
                    id="tax-rate"
                    type="number"
                    class="input"
                    min="0"
                    max="100"
                    step="0.01"
                    placeholder="e.g. 10"
                    bind:value={taxRate}
                  />
                </div>
                <div class="form-group">
                  <label for="tax-name" class="label">Tax Name</label>
                  <input
                    id="tax-name"
                    type="text"
                    class="input"
                    placeholder="e.g. VAT, GST, Sales Tax"
                    bind:value={taxName}
                  />
                </div>
              </div>
            {:else}
              <p class="form-hint" style="margin-top: var(--space-3);">Tax will be disabled for invoices to this client.</p>
            {/if}
          </div>
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
    max-width: 800px;
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

  .tax-override-section {
    margin-top: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  /* Responsive - Large screens */
  @media (min-width: 1400px) {
    .page-content {
      max-width: 900px;
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
