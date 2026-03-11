<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import InvoiceLineItemsCard from '$lib/components/invoices/InvoiceLineItemsCard.svelte';
  import InvoiceNotesCard from '$lib/components/invoices/InvoiceNotesCard.svelte';
  import InvoicePaymentInstructionsCard from '$lib/components/invoices/InvoicePaymentInstructionsCard.svelte';
  import InvoiceTaxCard from '$lib/components/invoices/InvoiceTaxCard.svelte';
  import { currencies } from '$lib/data/currencies';
  import { monthOptions, quarterMonthOptions, weekdayOptions } from '$lib/recurring/form';

  export let show = false;
  export let editingSchedule = null;
  export let formData;
  export let clients = [];
  export let availablePaymentMethods = [];
  export let defaultNotesText = '';
  export let smtpEnabled = false;
  export let saving = false;

  const dispatch = createEventDispatcher();

  function closeModal() {
    dispatch('close');
  }

  function saveSchedule() {
    dispatch('save');
  }

  function handleModalKeydown(event) {
    if (event.key === 'Escape') {
      closeModal();
    }
  }
</script>

{#if show}
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={handleModalKeydown}>
    <button type="button" class="modal-backdrop" aria-label="Close recurring schedule dialog" on:click={closeModal}></button>
    <div class="modal" role="dialog" aria-modal="true" tabindex="-1">
      <div class="modal-header">
        <h2>{editingSchedule ? 'Edit Schedule' : 'New Recurring Schedule'}</h2>
        <button class="btn btn-ghost btn-icon" on:click={closeModal}>
          <Icon name="x" size="md" />
        </button>
      </div>

      <div class="modal-body recurring-modal-body">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Schedule Details</h3>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="client" class="label">Client *</label>
              <select id="client" class="select" bind:value={formData.client_id}>
                <option value="">Select a client</option>
                {#each clients as client}
                  <option value={client.id}>{client.name || client.business_name}</option>
                {/each}
              </select>
            </div>

            <div class="form-group">
              <label for="name" class="label">Schedule Name *</label>
              <input
                id="name"
                type="text"
                class="input"
                placeholder="e.g., Monthly Retainer"
                bind:value={formData.name}
              />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="frequency" class="label">Frequency</label>
              <select id="frequency" class="select" bind:value={formData.frequency}>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="yearly">Yearly</option>
              </select>
            </div>

            <div class="form-group">
              <label for="currency" class="label">Currency</label>
              <select id="currency" class="select" bind:value={formData.currency_code}>
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

          <div class="timing-section">
            {#if formData.frequency === 'daily'}
              <p class="form-hint">Invoice will generate every day.</p>
            {:else if formData.frequency === 'weekly'}
              <div class="form-group">
                <label for="schedule-day" class="label">Day of Week</label>
                <select id="schedule-day" class="select" bind:value={formData.schedule_day}>
                  {#each weekdayOptions as option}
                    <option value={option.value}>{option.label}</option>
                  {/each}
                </select>
              </div>
            {:else if formData.frequency === 'monthly'}
              <div class="form-group">
                <label for="schedule-day" class="label">Day of Month</label>
                <input
                  id="schedule-day"
                  type="number"
                  class="input"
                  min="1"
                  max="31"
                  bind:value={formData.schedule_day}
                />
                <p class="form-hint">If a month has fewer days, the last day is used.</p>
              </div>
            {:else if formData.frequency === 'quarterly'}
              <div class="form-row">
                <div class="form-group">
                  <label for="quarter-month" class="label">Month in Quarter</label>
                  <select id="quarter-month" class="select" bind:value={formData.quarter_month}>
                    {#each quarterMonthOptions as option}
                      <option value={option.value}>{option.label}</option>
                    {/each}
                  </select>
                </div>

                <div class="form-group">
                  <label for="schedule-day" class="label">Day of Month</label>
                  <input
                    id="schedule-day"
                    type="number"
                    class="input"
                    min="1"
                    max="31"
                    bind:value={formData.schedule_day}
                  />
                </div>
              </div>
            {:else if formData.frequency === 'yearly'}
              <div class="form-row">
                <div class="form-group">
                  <label for="schedule-month" class="label">Month</label>
                  <select id="schedule-month" class="select" bind:value={formData.schedule_month}>
                    {#each monthOptions as option}
                      <option value={option.value}>{option.label}</option>
                    {/each}
                  </select>
                </div>

                <div class="form-group">
                  <label for="schedule-day" class="label">Day</label>
                  <input
                    id="schedule-day"
                    type="number"
                    class="input"
                    min="1"
                    max="31"
                    bind:value={formData.schedule_day}
                  />
                </div>
              </div>
            {/if}
          </div>

          <div class="form-group">
            <label for="terms" class="label">Payment Terms (days)</label>
            <input
              id="terms"
              type="number"
              class="input"
              min="0"
              max="365"
              bind:value={formData.payment_terms_days}
            />
          </div>
        </div>

        <InvoiceLineItemsCard
          bind:items={formData.line_items}
          bind:taxEnabled={formData.tax_enabled}
          bind:taxRate={formData.tax_rate}
          bind:taxName={formData.tax_name}
          addButtonText="Add Line Item"
        />

        <InvoiceTaxCard
          bind:taxEnabled={formData.tax_enabled}
          bind:taxRate={formData.tax_rate}
          bind:taxName={formData.tax_name}
          checkboxLabel="Apply Tax"
          disabledHint="Leave unchecked to use client or global default tax settings."
        />

        <InvoicePaymentInstructionsCard
          {availablePaymentMethods}
          bind:selectedPaymentMethods={formData.selected_payment_methods}
          bind:showPaymentInstructions={formData.show_payment_instructions}
          selectionHint="Select which payment methods to show on generated invoices."
        />

        <InvoiceNotesCard
          bind:useDefaultNotes={formData.use_default_notes}
          {defaultNotesText}
          bind:notes={formData.notes}
        />

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Automatic Email</h3>
          </div>

          {#if smtpEnabled}
            <label class="checkbox-label">
              <input type="checkbox" bind:checked={formData.auto_email_enabled} />
              <span>Automatically email invoice when generated</span>
            </label>

            {#if formData.auto_email_enabled}
              <p class="form-hint">Custom email templates are optional. Leave blank to use the defaults from Settings.</p>
              <div class="form-group">
                <label for="email-subject" class="label">Subject (optional)</label>
                <input
                  id="email-subject"
                  type="text"
                  class="input"
                  placeholder="e.g., Invoice &#123;invoice_number&#125; from &#123;business_name&#125;"
                  bind:value={formData.email_subject_template}
                />
              </div>
              <div class="form-group">
                <label for="email-body" class="label">Body (optional)</label>
                <textarea
                  id="email-body"
                  class="textarea"
                  rows="3"
                  placeholder="Custom email message..."
                  bind:value={formData.email_body_template}
                ></textarea>
              </div>
            {/if}
          {:else}
            <p class="form-hint">
              Configure SMTP in <a href="/settings" class="link">Settings</a> to enable automatic invoice emailing.
            </p>
          {/if}
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-ghost" on:click={closeModal}>Cancel</button>
        <button class="btn btn-primary" on:click={saveSchedule} disabled={saving}>
          {saving ? 'Saving...' : (editingSchedule ? 'Save Changes' : 'Create Schedule')}
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

  .recurring-modal-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .timing-section {
    margin-bottom: var(--space-4);
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 500;
  }

  .checkbox-label input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  .link {
    color: var(--color-primary);
    text-decoration: none;
  }

  .link:hover {
    text-decoration: underline;
  }
</style>
