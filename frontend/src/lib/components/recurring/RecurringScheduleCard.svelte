<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';
  import { formatFrequency, formatScheduleDate } from '$lib/recurring/form';

  export let schedule;
  export let isTriggering = false;

  const dispatch = createEventDispatcher();

  const clientLabel = schedule.client_name || schedule.client_business || 'Unknown Client';
</script>

<div class="schedule-card" class:inactive={!schedule.is_active}>
  <div class="schedule-header">
    <div class="schedule-info">
      <h3 class="schedule-name">{schedule.name}</h3>
      <p class="schedule-client">{clientLabel}</p>
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
      <span class="detail-value">{formatScheduleDate(schedule.next_invoice_date)}</span>
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
      on:click={() => dispatch('trigger')}
      disabled={isTriggering}
      title="Create invoice now"
    >
      {#if isTriggering}
        <span class="spinner-sm"></span>
      {:else}
        <Icon name="play" size="sm" />
      {/if}
      Generate Now
    </button>

    <button
      class="btn btn-ghost btn-sm"
      on:click={() => dispatch('toggle')}
      title={schedule.is_active ? 'Pause schedule' : 'Activate schedule'}
    >
      <Icon name={schedule.is_active ? 'pause' : 'play'} size="sm" />
    </button>

    <button class="btn btn-ghost btn-sm" on:click={() => dispatch('edit')} title="Edit schedule">
      <Icon name="pencil" size="sm" />
    </button>

    <button class="btn btn-ghost btn-sm btn-danger-text" on:click={() => dispatch('delete')} title="Delete schedule">
      <Icon name="trash" size="sm" />
    </button>
  </div>
</div>

<style>
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
    gap: var(--space-3);
  }

  .schedule-name {
    margin: 0;
    font-size: 1.0625rem;
    font-weight: 600;
  }

  .schedule-client {
    margin: var(--space-1) 0 0;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .schedule-status {
    padding: 0.25rem 0.625rem;
    border-radius: var(--radius-full);
    background: var(--color-bg-sunken);
    color: var(--color-text-secondary);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }

  .schedule-status.active {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  .schedule-details {
    display: grid;
    gap: var(--space-3);
    margin-bottom: var(--space-5);
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .detail-label {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .detail-value {
    color: var(--color-text);
    font-weight: 500;
    text-align: right;
  }

  .schedule-actions {
    display: flex;
    gap: var(--space-2);
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .spinner-sm {
    width: 14px;
    height: 14px;
    border: 2px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }
</style>
