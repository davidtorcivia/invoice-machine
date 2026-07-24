<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  
  
  /**
   * @typedef {Object} Props
   * @property {(detail?: any) => void} [oncopied]
   * @property {(detail?: any) => void} [oncopyfailed]
   * @property {(detail?: any) => void} [ontest]
   * @property {{ payments_enabled: boolean, stripe_secret_key_set: boolean, stripe_webhook_secret_set: boolean, webhook_url: string|null }} [settings]
   * @property {string} [secretKey] - Write-only fields; blank means "leave the stored value alone".
   * @property {string} [webhookSecret]
   * @property {boolean} [testing]
   */

  /** @type {Props} */
  let {
    settings = $bindable({
    payments_enabled: false,
    stripe_secret_key_set: false,
    stripe_webhook_secret_set: false,
    webhook_url: null
  }),
    secretKey = $bindable(''),
    webhookSecret = $bindable(''),
    testing = false, oncopied, oncopyfailed, ontest } = $props();

  async function copyWebhookUrl() {
    if (!settings.webhook_url) return;
    try {
      await navigator.clipboard.writeText(settings.webhook_url);
      oncopied?.();
    } catch (error) {
      oncopyfailed?.();
    }
  }
</script>

<CollapsibleSection title="Online payments" subtitle="Let clients pay invoices by card">
  <label class="checkbox-row">
    <input type="checkbox" bind:checked={settings.payments_enabled} />
    <span>Enable hosted payment links</span>
  </label>

  <p class="hint">
    Invoice Machine creates a Stripe Checkout link for each invoice's outstanding
    balance. Which card and wallet types appear is controlled from your Stripe
    dashboard.
  </p>

  <div class="form-group">
    <label for="stripe-key" class="label">
      Stripe API key
      {#if settings.stripe_secret_key_set}
        <span class="badge badge-paid">Saved</span>
      {/if}
    </label>
    <input
      id="stripe-key"
      bind:value={secretKey}
      type="password"
      class="input"
      autocomplete="off"
      placeholder={settings.stripe_secret_key_set ? 'Leave blank to keep the saved key' : 'rk_live_...'}
    />
    <p class="hint">
      Use a restricted key limited to Checkout Sessions rather than a full secret
      key, so a leaked value cannot move money or read your customer list. The key
      is encrypted before it is stored and is never shown again.
    </p>
  </div>

  <div class="form-group">
    <label for="stripe-webhook-secret" class="label">
      Webhook signing secret
      {#if settings.stripe_webhook_secret_set}
        <span class="badge badge-paid">Saved</span>
      {/if}
    </label>
    <input
      id="stripe-webhook-secret"
      bind:value={webhookSecret}
      type="password"
      class="input"
      autocomplete="off"
      placeholder={settings.stripe_webhook_secret_set ? 'Leave blank to keep the saved secret' : 'whsec_...'}
    />
    <p class="hint">
      Without this, completed payments cannot be verified and will not be recorded
      against the invoice.
    </p>
  </div>

  {#if settings.webhook_url}
    <div class="form-group">
      <span class="label">Webhook endpoint</span>
      <div class="webhook-row">
        <code class="webhook-url">{settings.webhook_url}</code>
        <button type="button" class="btn btn-secondary btn-sm" onclick={copyWebhookUrl}>
          Copy
        </button>
      </div>
      <p class="hint">
        Add this URL in Stripe under Developers, Webhooks, and subscribe it to
        <code>checkout.session.completed</code>.
      </p>
    </div>
  {/if}

  <button
    type="button"
    class="btn btn-secondary btn-sm"
    onclick={() => ontest?.()}
    disabled={testing || !settings.stripe_secret_key_set}
  >
    {testing ? 'Checking...' : 'Test credentials'}
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

  .webhook-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .webhook-url {
    flex: 1;
    min-width: 0;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm, 4px);
    font-size: 0.8rem;
    overflow-x: auto;
    white-space: nowrap;
  }
</style>
