<script>
  import { onMount } from 'svelte';
  import { recurringApi, clientsApi, profileApi } from '$lib/api';
  import { parseJsonArray } from '$lib/json';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import RecurringScheduleCard from '$lib/components/recurring/RecurringScheduleCard.svelte';
  import RecurringScheduleModal from '$lib/components/recurring/RecurringScheduleModal.svelte';
  import {
    buildSchedulePayload,
    createScheduleFormData,
    createScheduleFormDataFromSchedule
  } from '$lib/recurring/form';

  let schedules = [];
  let clients = [];
  let profile = null;
  let loading = true;
  let saving = false;
  let showModal = false;
  let editingSchedule = null;
  let formData = createScheduleFormData();

  let showDeleteModal = false;
  let deleteTarget = null;
  let deleting = false;
  let triggering = null;

  $: availablePaymentMethods = parseJsonArray(profile?.payment_methods);
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
    formData = createScheduleFormData();
    showModal = true;
  }

  function openEditModal(schedule) {
    editingSchedule = schedule;
    formData = createScheduleFormDataFromSchedule(schedule);
    showModal = true;
  }

  function closeModal() {
    showModal = false;
    editingSchedule = null;
    saving = false;
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

    saving = true;
    try {
      const data = buildSchedulePayload(formData);
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
    } finally {
      saving = false;
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
        <RecurringScheduleCard
          {schedule}
          isTriggering={triggering === schedule.id}
          on:trigger={() => triggerNow(schedule)}
          on:toggle={() => toggleActive(schedule)}
          on:edit={() => openEditModal(schedule)}
          on:delete={() => openDeleteModal(schedule)}
        />
      {/each}
    </div>
  {/if}
</div>

<RecurringScheduleModal
  show={showModal}
  {editingSchedule}
  bind:formData
  {clients}
  {availablePaymentMethods}
  {defaultNotesText}
  smtpEnabled={profile?.smtp_enabled}
  {saving}
  on:close={closeModal}
  on:save={saveSchedule}
/>

<ConfirmModal
  show={showDeleteModal}
  title="Delete Schedule"
  message="Are you sure you want to delete this recurring schedule? This cannot be undone."
  confirmText={deleting ? 'Deleting...' : 'Delete'}
  confirmVariant="danger"
  on:confirm={confirmDelete}
  on:cancel={() => {
    showDeleteModal = false;
    deleteTarget = null;
  }}
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
</style>
