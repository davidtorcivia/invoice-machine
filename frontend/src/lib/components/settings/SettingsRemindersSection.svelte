<script>
  import { createEventDispatcher } from 'svelte';
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  
  /**
   * @typedef {Object} Props
   * @property {{ reminders_enabled: boolean, reminder_offsets: number[], reminder_subject_template: string|null, reminder_body_template: string|null, smtp_enabled: boolean, business_timezone?: string, reminder_send_hour?: number, local_time?: string|null, default_subject?: string, default_body?: string }} [settings]
   * @property {boolean} [running]
   */

  /** @type {Props} */
  let { settings = $bindable({
    reminders_enabled: false,
    reminder_offsets: [-3, 1, 7, 14],
    reminder_subject_template: null,
    reminder_body_template: null,
    smtp_enabled: false,
    business_timezone: 'UTC',
    reminder_send_hour: 9
  }), running = false } = $props();

  const dispatch = createEventDispatcher();

  let newOffset = $state('');

  // Whatever the host platform knows about, so the list stays current without
  // shipping a hardcoded copy of the tz database.
  const timezones =
    typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : ['UTC'];
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  let hours = $derived(Array.from({ length: 24 }, (_, hour) => hour));

  function formatHour(hour) {
    const suffix = hour < 12 ? 'am' : 'pm';
    const display = hour % 12 === 0 ? 12 : hour % 12;
    return `${display}:00 ${suffix}`;
  }

  let offsets = $derived([...(settings.reminder_offsets || [])].sort((a, b) => a - b));

  function describeOffset(offset) {
    if (offset < 0) return `${Math.abs(offset)} days before due`;
    if (offset === 0) return 'on the due date';
    return `${offset} days after due`;
  }

  function addOffset() {
    const value = parseInt(newOffset, 10);
    if (Number.isNaN(value)) return;
    if (offsets.includes(value)) {
      newOffset = '';
      return;
    }
    settings.reminder_offsets = [...offsets, value].sort((a, b) => a - b);
    newOffset = '';
  }

  function removeOffset(offset) {
    settings.reminder_offsets = offsets.filter((value) => value !== offset);
  }
</script>

<CollapsibleSection
  title="Payment reminders"
  subtitle="Chase unpaid invoices automatically"
>
  <label class="checkbox-row">
    <input
      type="checkbox"
      bind:checked={settings.reminders_enabled}
      disabled={!settings.smtp_enabled}
    />
    <span>Send reminders automatically</span>
  </label>

  {#if !settings.smtp_enabled}
    <p class="hint warn">Configure SMTP above before turning reminders on.</p>
  {/if}

  <p class="hint">
    Reminders go out once a day to invoices that are sent or overdue and still
    have a balance. Each schedule point is sent at most once per invoice, and a
    fully paid invoice is never chased.
  </p>

  <div class="form-row">
    <div class="form-group">
      <label for="business-timezone" class="label">Your timezone</label>
      <select id="business-timezone" class="select" bind:value={settings.business_timezone}>
        {#each timezones as zone (zone)}
          <option value={zone}>{zone}</option>
        {/each}
      </select>
      <p class="hint">
        Sets when reminders send and how days until due are counted.
        {#if settings.local_time}
          Currently {settings.local_time} there.
        {/if}
        {#if browserZone && settings.business_timezone !== browserZone}
          This browser is in {browserZone}.
        {/if}
      </p>
    </div>

    <div class="form-group">
      <label for="reminder-hour" class="label">Send at</label>
      <select id="reminder-hour" class="select" bind:value={settings.reminder_send_hour}>
        {#each hours as hour (hour)}
          <option value={hour}>{formatHour(hour)}</option>
        {/each}
      </select>
    </div>
  </div>

  <div class="form-group">
    <span class="label">Schedule</span>
    {#if offsets.length === 0}
      <p class="hint">No reminders scheduled.</p>
    {:else}
      <ul class="offset-list">
        {#each offsets as offset (offset)}
          <li class="offset">
            <span>{describeOffset(offset)}</span>
            <button
              type="button"
              class="btn-danger-text"
              onclick={() => removeOffset(offset)}
              aria-label="Remove reminder {describeOffset(offset)}"
            >Remove</button>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="add-row">
      <label class="visually-hidden" for="reminder-offset">Days relative to due date</label>
      <input
        id="reminder-offset"
        bind:value={newOffset}
        type="number"
        class="input"
        min="-365"
        max="365"
        placeholder="e.g. 7"
        onkeydown={(event) => event.key === 'Enter' && (event.preventDefault(), addOffset())}
      />
      <button type="button" class="btn btn-secondary btn-sm" onclick={addOffset}>Add</button>
    </div>
    <p class="hint">
      Negative numbers are days before the due date, positive are days after.
    </p>
  </div>

  <div class="form-group">
    <label for="reminder-subject" class="label">Subject template</label>
    <input
      id="reminder-subject"
      bind:value={settings.reminder_subject_template}
      type="text"
      class="input"
      maxlength="500"
      placeholder={settings.default_subject || ''}
    />
  </div>

  <div class="form-group">
    <label for="reminder-body" class="label">Body template</label>
    <textarea
      id="reminder-body"
      bind:value={settings.reminder_body_template}
      class="textarea"
      rows="8"
      maxlength="10000"
      placeholder={settings.default_body || ''}
    ></textarea>
    <p class="hint">
      Leave blank to use the built-in wording. Reminder templates also accept
      <code>{'{amount_due}'}</code>, <code>{'{due_status}'}</code> and
      <code>{'{days_overdue}'}</code> alongside the usual invoice placeholders.
    </p>
  </div>

  <button
    type="button"
    class="btn btn-secondary btn-sm"
    onclick={() => dispatch('runnow')}
    disabled={running || !settings.reminders_enabled}
  >
    {running ? 'Sending...' : 'Send due reminders now'}
  </button>
</CollapsibleSection>

<style>
  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .hint {
    margin: 0.35rem 0 0;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    line-height: 1.5;
  }

  .hint.warn {
    color: var(--color-warning, #d97706);
  }

  .offset-list {
    list-style: none;
    margin: 0 0 0.6rem;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .offset {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    font-size: 0.88rem;
  }

  .add-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .add-row .input {
    max-width: 140px;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
</style>
