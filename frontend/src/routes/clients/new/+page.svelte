<script>
  import { goto } from '$app/navigation';
  import { clientsApi } from '$lib/api';
  import { createUnsavedGuard } from '$lib/unsavedGuard';
  import { toast } from '$lib/stores';
  import { countries } from '$lib/data/countries';
  import { currencies } from '$lib/data/currencies';
  import { buildClientPayload, createClientDraft } from '$lib/clients/config';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import ClientAddressSection from '$lib/components/clients/ClientAddressSection.svelte';
  import ClientIdentitySection from '$lib/components/clients/ClientIdentitySection.svelte';
  import ClientPreferencesSection from '$lib/components/clients/ClientPreferencesSection.svelte';
  import ClientTaxSettingsSection from '$lib/components/clients/ClientTaxSettingsSection.svelte';

  let saving = false;
  let showDiscardModal = false;
  let draft = createClientDraft();

  // Warn before leaving with unsaved edits (a stray sidebar click otherwise
  // silently discards the form).
  const guard = createUnsavedGuard(() => JSON.stringify(draft));
  guard.snapshot();

  async function saveClient() {
    if (!draft.name.trim() && !draft.business_name.trim()) {
      toast.error('Please enter a contact name or business name');
      return;
    }

    saving = true;
    try {
      const client = await clientsApi.create(buildClientPayload(draft));
      toast.success('Client created successfully');
      guard.allowLeave();
      goto(`/clients/${client.id}`);
    } catch (error) {
      toast.error('Failed to create client');
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
    goto('/clients');
  }
</script>

<Header title="New Client" subtitle="Add a new client to your contacts" />

<div class="page-content">
  <form on:submit|preventDefault={saveClient} class="form-layout">
    <ClientIdentitySection bind:name={draft.name} bind:businessName={draft.business_name} bind:email={draft.email} bind:phone={draft.phone} />
    <ClientAddressSection
      bind:addressLine1={draft.address_line1}
      bind:addressLine2={draft.address_line2}
      bind:city={draft.city}
      bind:state={draft.state}
      bind:postalCode={draft.postal_code}
      bind:country={draft.country}
      {countries}
    />
    <ClientPreferencesSection
      bind:paymentTermsDays={draft.payment_terms_days}
      bind:preferredCurrency={draft.preferred_currency}
      bind:notes={draft.notes}
      {currencies}
    />
    <ClientTaxSettingsSection
      bind:taxOverride={draft.tax_override}
      bind:taxEnabled={draft.tax_enabled}
      bind:taxRate={draft.tax_rate}
      bind:taxName={draft.tax_name}
    />

    <div class="form-actions">
      <button type="button" class="btn btn-secondary" on:click={cancel} disabled={saving}>Cancel</button>
      <button type="submit" class="btn btn-primary" disabled={saving}>
        <Icon name="check" size="sm" />
        {saving ? 'Creating...' : 'Create Client'}
      </button>
    </div>
  </form>
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
