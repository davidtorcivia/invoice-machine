<script>
  import { onMount } from 'svelte';
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import { paymentsApi, remindersApi } from '$lib/api';
  import { toast } from '$lib/stores';

  let open = false;
  let saving = false;
  let testing = false;
  let reminderOffsetsText = '-3, 0, 3, 7';
  let payments = {
    online_payments_enabled: false,
    payment_provider: '',
    stripe_secret_key: '',
    stripe_webhook_secret: '',
    stripe_secret_key_set: false,
    stripe_webhook_secret_set: false
  };
  let reminders = {
    reminders_enabled: false,
    reminder_offsets: [-3, 0, 3, 7],
    business_timezone: 'UTC',
    reminder_send_hour: 9,
    reminder_subject_template: '',
    reminder_body_template: ''
  };

  onMount(async () => {
    try {
      const [paymentData, reminderData] = await Promise.all([
        paymentsApi.getSettings(),
        remindersApi.getSettings()
      ]);
      payments = { ...payments, ...paymentData, payment_provider: paymentData.payment_provider || '' };
      reminders = { ...reminders, ...reminderData };
      reminderOffsetsText = reminderData.reminder_offsets.join(', ');
    } catch (error) {
      toast.error(error.message || 'Failed to load payment automation settings');
    }
  });

  async function save() {
    saving = true;
    try {
      const paymentPayload = {
        online_payments_enabled: payments.online_payments_enabled,
        payment_provider: payments.payment_provider || null
      };
      if (payments.stripe_secret_key) paymentPayload.stripe_secret_key = payments.stripe_secret_key;
      if (payments.stripe_webhook_secret) paymentPayload.stripe_webhook_secret = payments.stripe_webhook_secret;
      const offsets = reminderOffsetsText.split(',').map((value) => Number(value.trim()));
      const [paymentData, reminderData] = await Promise.all([
        paymentsApi.updateSettings(paymentPayload),
        remindersApi.updateSettings({ ...reminders, reminder_offsets: offsets })
      ]);
      payments = { ...payments, ...paymentData, stripe_secret_key: '', stripe_webhook_secret: '' };
      reminders = { ...reminders, ...reminderData };
      reminderOffsetsText = reminderData.reminder_offsets.join(', ');
      toast.success('Payment automation settings saved');
      return true;
    } catch (error) {
      toast.error(error.message || 'Failed to save payment automation settings');
      return false;
    } finally {
      saving = false;
    }
  }

  async function testProvider() {
    testing = true;
    try {
      if (!(await save())) return;
      const result = await paymentsApi.testProvider();
      toast.success(`Connected to ${result.provider}${result.test_mode ? ' in test mode' : ''}`);
    } catch (error) {
      toast.error(error.message || 'Provider connection failed');
    } finally {
      testing = false;
    }
  }
</script>

<CollapsibleSection bind:open title="Payments & reminders" subtitle="Optional automation for community self-hosters" icon="dollar">
  <div class="notice"><strong>Entirely optional.</strong> Invoice Machine keeps working with manual payments when no provider is configured. Credentials stay on this server.</div>
  <div class="settings-grid">
    <section>
      <h4>Online payments</h4>
      <label>Provider<select bind:value={payments.payment_provider} on:change={() => { if (!payments.payment_provider) payments.online_payments_enabled = false; }}><option value="">None</option><option value="stripe">Stripe</option></select></label>
      {#if payments.payment_provider === 'stripe'}
        <label>Secret key<input type="password" bind:value={payments.stripe_secret_key} placeholder={payments.stripe_secret_key_set ? 'Saved — leave blank to keep' : 'sk_test_…'} autocomplete="off" /></label>
        <label>Webhook signing secret<input type="password" bind:value={payments.stripe_webhook_secret} placeholder={payments.stripe_webhook_secret_set ? 'Saved — leave blank to keep' : 'whsec_…'} autocomplete="off" /></label>
        <p class="hint">Webhook endpoint: <code>/api/payments/stripe/webhook</code></p>
      {/if}
      <label class="check"><input type="checkbox" bind:checked={payments.online_payments_enabled} disabled={!payments.payment_provider} /> Allow payment links on invoices</label>
      {#if payments.payment_provider}<button class="btn btn-secondary" on:click={testProvider} disabled={testing || saving}>{testing ? 'Testing…' : 'Save & test provider'}</button>{/if}
    </section>
    <section>
      <h4>Email reminders</h4>
      <label class="check"><input type="checkbox" bind:checked={reminders.reminders_enabled} /> Enable scheduled reminders</label>
      <label>Days relative to due date<input bind:value={reminderOffsetsText} placeholder="-3, 0, 3, 7" /></label>
      <div class="row"><label>Timezone<input bind:value={reminders.business_timezone} placeholder="America/New_York" /></label><label>Send after hour<input type="number" min="0" max="23" bind:value={reminders.reminder_send_hour} /></label></div>
      <p class="hint">Negative days send before the due date. SMTP must also be enabled.</p>
    </section>
  </div>
  <div class="actions"><button class="btn btn-primary" on:click={save} disabled={saving}>{saving ? 'Saving…' : 'Save payments & reminders'}</button></div>
</CollapsibleSection>

<style>
  .notice { padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg); color: var(--color-text-secondary); }
  .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6); margin-top: var(--space-4); }
  section, label { display: grid; gap: var(--space-2); }
  section { align-content: start; }
  h4 { margin: 0 0 var(--space-2); }
  .check { display: flex; align-items: center; }
  .check input { width: auto; }
  .row { display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-3); }
  .hint { margin: 0; color: var(--color-text-secondary); font-size: .8125rem; }
  .actions { display: flex; justify-content: flex-end; margin-top: var(--space-4); }
  @media (max-width: 760px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
