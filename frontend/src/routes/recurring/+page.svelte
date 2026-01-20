<script>
  import { onMount } from 'svelte';
  import { recurringApi, clientsApi, profileApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';

  let schedules = [];
  let clients = [];
  let profile = null;
  let loading = true;
  let showModal = false;
  let editingSchedule = null;

  // Form data
  let formData = {
    client_id: '',
    name: '',
    frequency: 'monthly',
    schedule_day: 1,
    schedule_month: 1,
    quarter_month: 1,
    currency_code: 'USD',
    payment_terms_days: 30,
    notes: '',
    line_items: [],
    is_active: true,
    // Tax settings
    tax_enabled: null,
    tax_rate: '',
    tax_name: 'Tax',
    // Payment method selection
    show_payment_instructions: true,
    selected_payment_methods: [],
    // Auto-email settings
    auto_email_enabled: false,
    email_subject_template: '',
    email_body_template: '',
    // Notes toggle
    use_default_notes: true
  };

  // Line item being edited
  let newItem = { description: '', quantity: 1, unit_price: '', unit_type: 'qty' };

  // Delete modal
  let showDeleteModal = false;
  let deleteTarget = null;
  let deleting = false;

  // Trigger modal
  let triggering = null;

  // Computed: Available payment methods from profile
  $: availablePaymentMethods = (() => {
    if (!profile?.payment_methods) return [];
    try {
      return JSON.parse(profile.payment_methods);
    } catch {
      return [];
    }
  })();

  // Computed: Default notes from profile
  $: defaultNotesText = profile?.default_notes || '';

  onMount(async () => {
    await Promise.all([loadSchedules(), loadClients(), loadProfile()]);
  });

  async function loadSchedules() {
    loading = true;
    try {
      schedules = await recurringApi.list({ active_only: false });
    } catch (error) {
      toast.error('Failed to load recurring schedules');
    } finally {
      loading = false;
    }
  }

  async function loadClients() {
    try {
      clients = await clientsApi.list();
    } catch (error) {
      console.error('Failed to load clients:', error);
    }
  }

  async function loadProfile() {
    try {
      profile = await profileApi.get();
    } catch (error) {
      console.error('Failed to load profile:', error);
    }
  }

  function openCreateModal() {
    editingSchedule = null;
    formData = {
      client_id: '',
      name: '',
      frequency: 'monthly',
      schedule_day: 1,
      schedule_month: 1,
      quarter_month: 1,
      currency_code: 'USD',
      payment_terms_days: 30,
      notes: '',
      line_items: [],
      is_active: true,
      tax_enabled: null,
      tax_rate: '',
      tax_name: 'Tax',
      show_payment_instructions: true,
      selected_payment_methods: [],
      auto_email_enabled: false,
      email_subject_template: '',
      email_body_template: '',
      use_default_notes: true
    };
    newItem = { description: '', quantity: 1, unit_price: '', unit_type: 'qty' };
    showModal = true;
  }

  function openEditModal(schedule) {
    editingSchedule = schedule;
    formData = {
      client_id: schedule.client_id,
      name: schedule.name,
      frequency: schedule.frequency,
      schedule_day: schedule.schedule_day,
      schedule_month: schedule.schedule_month || 1,
      quarter_month: schedule.quarter_month || 1,
      currency_code: schedule.currency_code,
      payment_terms_days: schedule.payment_terms_days,
      notes: schedule.notes || '',
      line_items: schedule.line_items ? [...schedule.line_items] : [],
      is_active: schedule.is_active,
      tax_enabled: schedule.tax_enabled,
      tax_rate: schedule.tax_rate || '',
      tax_name: schedule.tax_name || 'Tax',
      show_payment_instructions: schedule.show_payment_instructions !== false,
      selected_payment_methods: schedule.selected_payment_methods || [],
      auto_email_enabled: schedule.auto_email_enabled || false,
      email_subject_template: schedule.email_subject_template || '',
      email_body_template: schedule.email_body_template || '',
      use_default_notes: schedule.use_default_notes !== false
    };
    newItem = { description: '', quantity: 1, unit_price: '', unit_type: 'qty' };
    showModal = true;
  }

  function closeModal() {
    showModal = false;
    editingSchedule = null;
  }

  function addLineItem() {
    if (!newItem.description || !newItem.unit_price) {
      toast.error('Please enter description and price');
      return;
    }
    formData.line_items = [...formData.line_items, { ...newItem }];
    newItem = { description: '', quantity: 1, unit_price: '', unit_type: 'qty' };
  }

  function removeLineItem(index) {
    formData.line_items = formData.line_items.filter((_, i) => i !== index);
  }

  async function saveSchedule() {
    if (!formData.client_id) {
      toast.error('Please select a client');
      return;
    }
    if (!formData.name) {
      toast.error('Please enter a schedule name');
      return;
    }

    try {
      const data = {
        ...formData,
        client_id: parseInt(formData.client_id),
        schedule_day: parseInt(formData.schedule_day),
        schedule_month: formData.frequency === 'yearly' ? parseInt(formData.schedule_month) : null,
        quarter_month: formData.frequency === 'quarterly' ? parseInt(formData.quarter_month) : 1,
        payment_terms_days: parseInt(formData.payment_terms_days),
        // Handle tax_rate conversion
        tax_rate: formData.tax_enabled && formData.tax_rate ? parseFloat(formData.tax_rate) : null,
        // If using default notes, send empty notes so backend will use profile default
        notes: formData.use_default_notes ? '' : formData.notes
      };

      if (editingSchedule) {
        await recurringApi.update(editingSchedule.id, data);
        toast.success('Schedule updated');
      } else {
        await recurringApi.create(data);
        toast.success('Schedule created');
      }

      closeModal();
      await loadSchedules();
    } catch (error) {
      toast.error(error.message || 'Failed to save schedule');
    }
  }

  function openDeleteModal(schedule) {
    deleteTarget = schedule;
    showDeleteModal = true;
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    deleting = true;
    try {
      await recurringApi.delete(deleteTarget.id);
      toast.success('Schedule deleted');
      showDeleteModal = false;
      deleteTarget = null;
      await loadSchedules();
    } catch (error) {
      toast.error('Failed to delete schedule');
    } finally {
      deleting = false;
    }
  }

  async function toggleActive(schedule) {
    try {
      await recurringApi.update(schedule.id, { is_active: !schedule.is_active });
      await loadSchedules();
      toast.success(schedule.is_active ? 'Schedule paused' : 'Schedule activated');
    } catch (error) {
      toast.error('Failed to update schedule');
    }
  }

  async function triggerNow(schedule) {
    triggering = schedule.id;
    try {
      const result = await recurringApi.trigger(schedule.id);
      toast.success(`Invoice ${result.invoice_number} created`);
      await loadSchedules();
    } catch (error) {
      toast.error(error.message || 'Failed to create invoice');
    } finally {
      triggering = null;
    }
  }

  function formatFrequency(freq) {
    const labels = {
      daily: 'Daily',
      weekly: 'Weekly',
      monthly: 'Monthly',
      quarterly: 'Quarterly',
      yearly: 'Yearly'
    };
    return labels[freq] || freq;
  }

  function formatDate(dateStr) {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString();
  }
</script>

<Header title="Recurring Invoices" subtitle="Automate your billing with scheduled invoices" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Recurring Invoices</h1>
      <p class="page-subtitle">{schedules.length} schedule{schedules.length !== 1 ? 's' : ''}</p>
    </div>
    <button class="btn btn-primary" on:click={openCreateModal}>
      <Icon name="plus" size="sm" />
      New Schedule
    </button>
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if schedules.length === 0}
    <div class="empty-state">
      <div class="empty-icon">
        <Icon name="repeat" size="xl" />
      </div>
      <h3>No Recurring Schedules</h3>
      <p>Create a recurring schedule to automatically generate invoices on a regular basis.</p>
      <button class="btn btn-primary" on:click={openCreateModal}>
        <Icon name="plus" size="sm" />
        Create First Schedule
      </button>
    </div>
  {:else}
    <div class="schedules-grid">
      {#each schedules as schedule}
        <div class="schedule-card" class:inactive={!schedule.is_active}>
          <div class="schedule-header">
            <div class="schedule-info">
              <h3 class="schedule-name">{schedule.name}</h3>
              <p class="schedule-client">{schedule.client_name || schedule.client_business || 'Unknown Client'}</p>
            </div>
            <div class="schedule-status" class:active={schedule.is_active}>
              {schedule.is_active ? 'Active' : 'Paused'}
            </div>
          </div>

          <div class="schedule-details">
            <div class="detail-row">
              <span class="detail-label">Frequency</span>
              <span class="detail-value">{formatFrequency(schedule.frequency)}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Next Invoice</span>
              <span class="detail-value">{formatDate(schedule.next_invoice_date)}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Currency</span>
              <span class="detail-value">{schedule.currency_code}</span>
            </div>
            {#if schedule.line_items && schedule.line_items.length > 0}
              <div class="detail-row">
                <span class="detail-label">Line Items</span>
                <span class="detail-value">{schedule.line_items.length} item(s)</span>
              </div>
            {/if}
          </div>

          <div class="schedule-actions">
            <button
              class="btn btn-secondary btn-sm"
              on:click={() => triggerNow(schedule)}
              disabled={triggering === schedule.id}
              title="Create invoice now"
            >
              {#if triggering === schedule.id}
                <span class="spinner-sm"></span>
              {:else}
                <Icon name="play" size="sm" />
              {/if}
              Generate Now
            </button>

            <button
              class="btn btn-ghost btn-sm"
              on:click={() => toggleActive(schedule)}
              title={schedule.is_active ? 'Pause schedule' : 'Activate schedule'}
            >
              <Icon name={schedule.is_active ? 'pause' : 'play'} size="sm" />
            </button>

            <button
              class="btn btn-ghost btn-sm"
              on:click={() => openEditModal(schedule)}
              title="Edit schedule"
            >
              <Icon name="pencil" size="sm" />
            </button>

            <button
              class="btn btn-ghost btn-sm btn-danger-text"
              on:click={() => openDeleteModal(schedule)}
              title="Delete schedule"
            >
              <Icon name="trash" size="sm" />
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Create/Edit Modal -->
{#if showModal}
  <div class="modal-overlay" on:click={closeModal} on:keydown={(e) => e.key === 'Escape' && closeModal()}>
    <div class="modal" on:click|stopPropagation>
      <div class="modal-header">
        <h2>{editingSchedule ? 'Edit Schedule' : 'New Recurring Schedule'}</h2>
        <button class="btn btn-ghost btn-icon" on:click={closeModal}>
          <Icon name="x" size="md" />
        </button>
      </div>

      <div class="modal-body">
        <div class="form-row">
          <div class="form-group">
            <label for="client" class="label">Client *</label>
            <select id="client" class="input" bind:value={formData.client_id}>
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

        <div class="form-group">
          <label for="frequency" class="label">Frequency</label>
          <select id="frequency" class="input" bind:value={formData.frequency}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="yearly">Yearly</option>
          </select>
        </div>

        <!-- Schedule timing based on frequency -->
        {#if formData.frequency === 'daily'}
          <p class="form-hint">Invoice will generate every day.</p>
        {:else if formData.frequency === 'weekly'}
          <div class="form-group">
            <label for="schedule_day" class="label">Day of Week</label>
            <select id="schedule_day" class="input" bind:value={formData.schedule_day}>
              <option value={0}>Monday</option>
              <option value={1}>Tuesday</option>
              <option value={2}>Wednesday</option>
              <option value={3}>Thursday</option>
              <option value={4}>Friday</option>
              <option value={5}>Saturday</option>
              <option value={6}>Sunday</option>
            </select>
          </div>
        {:else if formData.frequency === 'monthly'}
          <div class="form-group">
            <label for="schedule_day" class="label">Day of Month</label>
            <input
              id="schedule_day"
              type="number"
              class="input"
              min="1"
              max="31"
              bind:value={formData.schedule_day}
            />
            <p class="form-hint">If month has fewer days, last day will be used.</p>
          </div>
        {:else if formData.frequency === 'quarterly'}
          <div class="form-row">
            <div class="form-group">
              <label for="quarter_month" class="label">Month in Quarter</label>
              <select id="quarter_month" class="input" bind:value={formData.quarter_month}>
                <option value={1}>1st month (Jan, Apr, Jul, Oct)</option>
                <option value={2}>2nd month (Feb, May, Aug, Nov)</option>
                <option value={3}>3rd month (Mar, Jun, Sep, Dec)</option>
              </select>
            </div>
            <div class="form-group">
              <label for="schedule_day" class="label">Day of Month</label>
              <input
                id="schedule_day"
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
              <label for="schedule_month" class="label">Month</label>
              <select id="schedule_month" class="input" bind:value={formData.schedule_month}>
                <option value={1}>January</option>
                <option value={2}>February</option>
                <option value={3}>March</option>
                <option value={4}>April</option>
                <option value={5}>May</option>
                <option value={6}>June</option>
                <option value={7}>July</option>
                <option value={8}>August</option>
                <option value={9}>September</option>
                <option value={10}>October</option>
                <option value={11}>November</option>
                <option value={12}>December</option>
              </select>
            </div>
            <div class="form-group">
              <label for="schedule_day" class="label">Day</label>
              <input
                id="schedule_day"
                type="number"
                class="input"
                min="1"
                max="31"
                bind:value={formData.schedule_day}
              />
            </div>
          </div>
        {/if}

        <div class="form-row">
          <div class="form-group">
            <label for="currency" class="label">Currency</label>
            <select id="currency" class="input" bind:value={formData.currency_code}>
              {#each currencies as currency}
                {#if currency.disabled}
                  <option value="" disabled>{currency.name}</option>
                {:else}
                  <option value={currency.code}>{currency.code} - {currency.name}</option>
                {/if}
              {/each}
            </select>
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

        <!-- Line Items Section -->
        <div class="section-divider">
          <span>Line Items</span>
        </div>

        {#if formData.line_items.length > 0}
          <div class="line-items-list">
            {#each formData.line_items as item, index}
              <div class="line-item">
                <div class="line-item-info">
                  <span class="line-item-desc">{item.description}</span>
                  <span class="line-item-details">
                    {item.quantity} {item.unit_type === 'hours' ? 'hrs' : 'x'} ${item.unit_price}{item.unit_type === 'hours' ? '/hr' : ''}
                  </span>
                </div>
                <button class="btn btn-ghost btn-icon btn-sm" on:click={() => removeLineItem(index)}>
                  <Icon name="x" size="sm" />
                </button>
              </div>
            {/each}
          </div>
        {/if}

        <div class="add-item-form">
          <input
            type="text"
            class="input"
            placeholder="Description"
            bind:value={newItem.description}
          />
          <select class="input input-sm" bind:value={newItem.unit_type}>
            <option value="qty">Qty</option>
            <option value="hours">Hours</option>
          </select>
          <input
            type="number"
            class="input input-sm"
            placeholder={newItem.unit_type === 'hours' ? 'Hours' : 'Qty'}
            min="1"
            step={newItem.unit_type === 'hours' ? '0.5' : '1'}
            bind:value={newItem.quantity}
          />
          <input
            type="number"
            class="input input-sm"
            placeholder={newItem.unit_type === 'hours' ? 'Rate' : 'Price'}
            step="0.01"
            bind:value={newItem.unit_price}
          />
          <button class="btn btn-secondary btn-sm" on:click={addLineItem}>
            <Icon name="plus" size="sm" />
          </button>
        </div>

        <!-- Tax Settings Section -->
        <div class="section-divider">
          <span>Tax Settings</span>
        </div>

        <label class="checkbox-label">
          <input type="checkbox" bind:checked={formData.tax_enabled} />
          <span>Apply Tax</span>
        </label>

        {#if formData.tax_enabled}
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
                bind:value={formData.tax_rate}
              />
            </div>
            <div class="form-group">
              <label for="tax-name" class="label">Tax Name</label>
              <input
                id="tax-name"
                type="text"
                class="input"
                placeholder="Tax, VAT, GST, etc."
                bind:value={formData.tax_name}
              />
            </div>
          </div>
        {:else}
          <p class="form-hint">Leave unchecked to use client or global default tax settings.</p>
        {/if}

        <!-- Payment Methods Section -->
        <div class="section-divider">
          <span>Payment Instructions</span>
        </div>

        {#if availablePaymentMethods.length > 0}
          <p class="form-hint">Select which payment methods to show on generated invoices.</p>
          <div class="payment-methods-list">
            {#each availablePaymentMethods as method}
              <label class="checkbox-label payment-method-option">
                <input
                  type="checkbox"
                  checked={formData.selected_payment_methods.includes(method.id)}
                  on:change={(e) => {
                    if (e.target.checked) {
                      formData.selected_payment_methods = [...formData.selected_payment_methods, method.id];
                    } else {
                      formData.selected_payment_methods = formData.selected_payment_methods.filter(id => id !== method.id);
                    }
                  }}
                />
                <span>{method.name}</span>
              </label>
            {/each}
          </div>
        {:else}
          <label class="checkbox-label">
            <input type="checkbox" bind:checked={formData.show_payment_instructions} />
            <span>Include Payment Instructions</span>
          </label>
          <p class="form-hint">Configure payment methods in Settings to select specific ones.</p>
        {/if}

        <!-- Notes Section -->
        <div class="section-divider">
          <span>Notes</span>
        </div>

        {#if formData.use_default_notes && defaultNotesText}
          <div class="default-notes-display">
            <div class="default-notes-header">
              <span class="default-notes-label">Using default notes from Settings</span>
              <button type="button" class="btn btn-ghost btn-sm" on:click={() => { formData.use_default_notes = false; }}>
                Customize
              </button>
            </div>
            <div class="default-notes-content">{defaultNotesText}</div>
          </div>
        {:else}
          <textarea
            id="notes"
            class="textarea"
            rows="2"
            placeholder="Payment terms, thank you message, etc."
            bind:value={formData.notes}
          ></textarea>
          {#if defaultNotesText}
            <button type="button" class="btn btn-ghost btn-sm mt-2" on:click={() => { formData.use_default_notes = true; formData.notes = ''; }}>
              Use default notes
            </button>
          {/if}
        {/if}

        <!-- Auto-Email Section -->
        <div class="section-divider">
          <span>Automatic Email</span>
        </div>

        {#if profile?.smtp_enabled}
          <label class="checkbox-label">
            <input type="checkbox" bind:checked={formData.auto_email_enabled} />
            <span>Automatically email invoice when generated</span>
          </label>

          {#if formData.auto_email_enabled}
            <p class="form-hint">Custom email templates (leave blank to use defaults from Settings):</p>
            <div class="form-group">
              <label for="email-subject" class="label">Subject (optional)</label>
              <input
                id="email-subject"
                type="text"
                class="input"
                placeholder="e.g., Invoice {invoice_number} from {business_name}"
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

      <div class="modal-footer">
        <button class="btn btn-ghost" on:click={closeModal}>Cancel</button>
        <button class="btn btn-primary" on:click={saveSchedule}>
          {editingSchedule ? 'Save Changes' : 'Create Schedule'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Delete Confirmation Modal -->
<ConfirmModal
  show={showDeleteModal}
  title="Delete Schedule"
  message="Are you sure you want to delete this recurring schedule? This cannot be undone."
  confirmText={deleting ? 'Deleting...' : 'Delete'}
  confirmVariant="danger"
  on:confirm={confirmDelete}
  on:cancel={() => { showDeleteModal = false; deleteTarget = null; }}
/>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 1400px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-6);
    gap: var(--space-4);
  }

  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .page-subtitle {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    margin: var(--space-1) 0 0 0;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-10);
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }

  .empty-state {
    text-align: center;
    padding: var(--space-10);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .empty-icon {
    color: var(--color-text-muted);
    margin-bottom: var(--space-4);
  }

  .empty-state h3 {
    margin: 0 0 var(--space-2);
    color: var(--color-text);
  }

  .empty-state p {
    color: var(--color-text-secondary);
    margin-bottom: var(--space-4);
  }

  .schedules-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: var(--space-4);
  }

  .schedule-card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
  }

  .schedule-card.inactive {
    opacity: 0.7;
  }

  .schedule-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: var(--space-4);
  }

  .schedule-name {
    margin: 0;
    font-size: 1.0625rem;
    font-weight: 600;
  }

  .schedule-client {
    margin: var(--space-1) 0 0;
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .schedule-status {
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
    background: var(--color-bg-sunken);
    color: var(--color-text-secondary);
  }

  .schedule-status.active {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  .schedule-details {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-bottom: var(--space-4);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--color-border);
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
  }

  .detail-label {
    color: var(--color-text-secondary);
  }

  .detail-value {
    font-weight: 500;
  }

  .schedule-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  /* Modal styles */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    padding: var(--space-4);
  }

  .modal {
    background: var(--color-bg-elevated);
    border-radius: var(--radius-xl);
    width: 100%;
    max-width: 600px;
    max-height: 90vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--color-border);
  }

  .modal-header h2 {
    margin: 0;
    font-size: 1.125rem;
  }

  .modal-body {
    padding: var(--space-6);
    overflow-y: auto;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-6);
    border-top: 1px solid var(--color-border);
  }

  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
    margin-bottom: var(--space-4);
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .section-divider {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin: var(--space-5) 0 var(--space-4);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .section-divider::before,
  .section-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--color-border);
  }

  .line-items-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-bottom: var(--space-3);
  }

  .line-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
  }

  .line-item-desc {
    font-weight: 500;
  }

  .line-item-details {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .add-item-form {
    display: flex;
    gap: var(--space-2);
    margin-bottom: var(--space-4);
  }

  .add-item-form .input:first-child {
    flex: 2;
  }

  .add-item-form .input-sm {
    width: 70px;
    flex: none;
  }

  /* Form hint text */
  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-muted);
    margin: var(--space-2) 0;
  }

  .form-hint a {
    color: var(--color-primary);
    text-decoration: none;
  }

  .form-hint a:hover {
    text-decoration: underline;
  }

  /* Checkbox label */
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-size: 0.9375rem;
    margin-bottom: var(--space-2);
  }

  .checkbox-label input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
    cursor: pointer;
  }

  /* Tax fields row */
  .tax-fields {
    margin-top: var(--space-3);
  }

  /* Payment methods list */
  .payment-methods-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  .payment-method-option {
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
  }

  /* Default notes display */
  .default-notes-display {
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    padding: var(--space-3);
  }

  .default-notes-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-2);
  }

  .default-notes-label {
    font-size: 0.8125rem;
    color: var(--color-text-muted);
  }

  .default-notes-content {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    white-space: pre-wrap;
  }

  /* Utility */
  .mt-2 {
    margin-top: var(--space-2);
  }

  .spinner-sm {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
    display: inline-block;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .page-header {
      flex-direction: column;
      align-items: flex-start;
    }
  }

  @media (max-width: 640px) {
    .form-row {
      grid-template-columns: 1fr;
    }

    .add-item-form {
      flex-wrap: wrap;
    }

    .add-item-form .input:first-child {
      width: 100%;
      flex: none;
    }
  }

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }
  }
</style>
