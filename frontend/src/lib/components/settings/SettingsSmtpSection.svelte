<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let open = false;
  export let smtpEnabled = false;
  export let smtpHost = '';
  export let smtpPort = 587;
  export let smtpUsername = '';
  export let smtpPassword = '';
  export let smtpFromEmail = '';
  export let smtpFromName = '';
  export let smtpUseTls = true;
  export let smtpPasswordSet = false;
  export let testingSmtp = false;
  export let savingSmtp = false;
  export let testSmtpConnection;
  export let saveSmtpSettings;
</script>

<CollapsibleSection title="Email Settings (SMTP)" subtitle="Send invoices via email" icon="send" bind:open={open}>
  <p class="form-hint mb-4">
    Configure SMTP to send invoices directly via email. Leave disabled if you prefer to download and send PDFs manually.
  </p>

  <div class="form-group">
    <label class="toggle-container">
      <input type="checkbox" bind:checked={smtpEnabled} />
      <span class="toggle-label">Enable email sending</span>
    </label>
  </div>

  {#if smtpEnabled}
    <div class="form-row">
      <div class="form-group">
        <label for="smtp-host" class="label">SMTP Host *</label>
        <input
          id="smtp-host"
          type="text"
          class="input"
          placeholder="smtp.example.com"
          bind:value={smtpHost}
        />
      </div>

      <div class="form-group">
        <label for="smtp-port" class="label">Port</label>
        <input
          id="smtp-port"
          type="number"
          class="input"
          placeholder="587"
          bind:value={smtpPort}
        />
      </div>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label for="smtp-username" class="label">Username</label>
        <input
          id="smtp-username"
          type="text"
          class="input"
          placeholder="your@email.com"
          bind:value={smtpUsername}
        />
      </div>

      <div class="form-group">
        <label for="smtp-password" class="label">Password {smtpPasswordSet ? '(set)' : ''}</label>
        <input
          id="smtp-password"
          type="password"
          class="input"
          placeholder={smtpPasswordSet ? '••••••••' : 'Enter password'}
          bind:value={smtpPassword}
        />
        <p class="form-hint">Leave empty to keep existing password</p>
      </div>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label for="smtp-from-email" class="label">From Email *</label>
        <input
          id="smtp-from-email"
          type="email"
          class="input"
          placeholder="invoices@example.com"
          bind:value={smtpFromEmail}
        />
      </div>

      <div class="form-group">
        <label for="smtp-from-name" class="label">From Name</label>
        <input
          id="smtp-from-name"
          type="text"
          class="input"
          placeholder="Your Business Name"
          bind:value={smtpFromName}
        />
      </div>
    </div>

    <div class="form-group">
      <label class="toggle-container">
        <input type="checkbox" bind:checked={smtpUseTls} />
        <span class="toggle-label">Use TLS encryption</span>
      </label>
      <p class="form-hint">Recommended for security. Use port 587 for STARTTLS or 465 for SSL.</p>
    </div>

    <div class="form-actions">
      <button
        type="button"
        class="btn btn-secondary"
        on:click={testSmtpConnection}
        disabled={testingSmtp || !smtpHost || !smtpFromEmail}
      >
        {#if testingSmtp}
          <span class="spinner-sm"></span>
          Testing...
        {:else}
          <Icon name="send" size="sm" />
          Test Connection
        {/if}
      </button>

      <button
        type="button"
        class="btn btn-primary"
        on:click={saveSmtpSettings}
        disabled={savingSmtp}
      >
        {#if savingSmtp}
          <span class="spinner-sm"></span>
          Saving...
        {:else}
          Save SMTP Settings
        {/if}
      </button>
    </div>

    <div class="template-link">
      <a href="/settings/email-templates" class="btn btn-ghost">
        <Icon name="pencil" size="sm" />
        Configure Email Templates
      </a>
      <p class="form-hint">Customize the default subject and body for invoice emails</p>
    </div>
  {/if}
</CollapsibleSection>

<style>
  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  .mb-4 {
    margin-bottom: var(--space-4);
  }

  .toggle-container {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    user-select: none;
  }

  .toggle-container input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
    cursor: pointer;
  }

  .toggle-label {
    font-weight: 500;
    color: var(--color-text);
  }

  .form-actions {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .template-link {
    margin-top: var(--space-4);
  }

  .template-link .form-hint {
    margin-top: var(--space-2);
  }
</style>
