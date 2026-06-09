<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let show = false;
  export let documentLabel = 'Invoice';
  export let emailLoading = false;
  export let emailSending = false;
  export let emailRecipient = '';
  export let emailSubject = '';
  export let emailBody = '';

  const dispatch = createEventDispatcher();

  function handleKeydown(event) {
    if (event.key === 'Escape') {
      dispatch('cancel');
    }
  }
</script>

{#if show}
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={handleKeydown}>
    <button type="button" class="modal-backdrop" aria-label="Close send email dialog" on:click={() => dispatch('cancel')}></button>
    <div class="modal-content email-modal" role="dialog" aria-modal="true" tabindex="-1">
      <div class="modal-header">
        <h2 class="modal-title">
          <Icon name="send" size="md" />
          Send {documentLabel} via Email
        </h2>
        <button class="btn btn-ghost btn-sm" aria-label="Close" on:click={() => dispatch('cancel')}>
          <Icon name="x" size="sm" />
        </button>
      </div>

      {#if emailLoading}
        <div class="modal-loading">
          <div class="spinner"></div>
          <p>Loading email preview...</p>
        </div>
      {:else}
        <div class="modal-body">
          <div class="form-group">
            <label for="email-recipient" class="form-label">Recipient Email *</label>
            <input
              id="email-recipient"
              type="email"
              class="input"
              bind:value={emailRecipient}
              placeholder="client@example.com"
              required
            />
          </div>

          <div class="form-group">
            <label for="email-subject" class="form-label">Subject</label>
            <input id="email-subject" type="text" class="input" bind:value={emailSubject} />
          </div>

          <div class="form-group">
            <label for="email-body" class="form-label">Message</label>
            <textarea id="email-body" class="input email-body-input" bind:value={emailBody} rows="10"></textarea>
          </div>

          <p class="form-hint">
            <Icon name="invoice" size="sm" />
            The PDF will be attached automatically.
          </p>
        </div>

        <div class="modal-actions">
          <button class="btn btn-ghost" on:click={() => dispatch('cancel')}>Cancel</button>
          <button class="btn btn-primary" on:click={() => dispatch('confirm')} disabled={emailSending || !emailRecipient}>
            {#if emailSending}
              <span class="spinner-sm"></span>
              Sending...
            {:else}
              <Icon name="send" size="sm" />
              Send Email
            {/if}
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: var(--space-4);
  }

  .modal-content {
    position: relative;
    background: var(--color-bg-elevated);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-xl);
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
  }

  .email-modal {
    max-width: 700px;
  }

  .modal-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--color-border-light);
  }

  .modal-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .modal-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    padding: var(--space-8);
    color: var(--color-text-secondary);
  }

  .modal-body {
    padding: var(--space-6);
  }

  .form-group {
    margin-bottom: var(--space-4);
  }

  .form-label {
    display: block;
    font-weight: 500;
    color: var(--color-text);
    margin-bottom: var(--space-2);
  }

  .input {
    width: 100%;
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.875rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .input:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px var(--color-primary-light);
  }

  .email-body-input {
    resize: vertical;
    font-family: inherit;
    line-height: 1.5;
  }

  .form-hint {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-6);
    border-top: 1px solid var(--color-border-light);
    background: var(--color-bg-sunken);
    border-radius: 0 0 var(--radius-xl) var(--radius-xl);
  }

  .spinner-sm,
  .spinner {
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
    display: inline-block;
  }

  .spinner-sm {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-top-color: transparent;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
