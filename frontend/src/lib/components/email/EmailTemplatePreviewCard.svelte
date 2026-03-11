<script>
  import Icon from '$lib/components/Icons.svelte';

  export let invoices = [];
  export let previewInvoiceId = null;
  export let previewLoading = false;
  export let previewSubject = '';
  export let previewBody = '';
  export let updatePreview;
</script>

<div class="preview-panel">
  <div class="card sticky">
    <div class="card-header">
      <h3 class="card-title">Preview</h3>
      {#if invoices.length > 0}
        <select class="preview-select" bind:value={previewInvoiceId} on:change={updatePreview}>
          {#each invoices as invoice}
            <option value={invoice.id}>
              {invoice.invoice_number} - {invoice.client_business || invoice.client_name || 'No client'}
            </option>
          {/each}
        </select>
      {/if}
    </div>

    {#if previewLoading}
      <div class="preview-loading">
        <div class="spinner-sm"></div>
        Loading preview...
      </div>
    {:else if previewSubject || previewBody}
      <div class="preview-content">
        <div class="preview-field">
          <span class="preview-label">Subject:</span>
          <span class="preview-value">{previewSubject}</span>
        </div>
        <div class="preview-divider"></div>
        <div class="preview-body">
          <pre>{previewBody}</pre>
        </div>
      </div>
    {:else}
      <div class="preview-empty">
        <Icon name="mail" size="lg" />
        <p>{invoices.length > 0 ? 'No preview available' : 'Create an invoice first to see the email preview'}</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
  }

  .sticky {
    position: sticky;
    top: var(--space-4);
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-4);
    gap: var(--space-3);
  }

  .card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .preview-select {
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.8125rem;
    max-width: 200px;
  }

  .preview-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: var(--space-8);
    color: var(--color-text-secondary);
  }

  .preview-content {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .preview-field {
    display: flex;
    gap: var(--space-2);
    padding: var(--space-3);
    border-bottom: 1px solid var(--color-border-light);
  }

  .preview-label {
    font-weight: 500;
    color: var(--color-text-secondary);
    white-space: nowrap;
  }

  .preview-value {
    color: var(--color-text);
  }

  .preview-divider {
    height: 1px;
    background: var(--color-border-light);
  }

  .preview-body {
    padding: var(--space-4);
  }

  .preview-body pre {
    margin: 0;
    white-space: pre-wrap;
    font-family: inherit;
    font-size: 0.875rem;
    line-height: 1.6;
    color: var(--color-text);
  }

  .preview-empty {
    text-align: center;
    padding: var(--space-8);
    color: var(--color-text-secondary);
  }

  .preview-empty p {
    margin: var(--space-2) 0 0;
  }

  .spinner-sm {
    width: 16px;
    height: 16px;
    border: 2px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 1024px) {
    .sticky {
      position: static;
    }
  }
</style>
