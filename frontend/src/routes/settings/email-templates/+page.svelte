<script>
  import { onMount } from 'svelte';
  import { emailApi, invoicesApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let loading = true;
  let saving = false;
  let previewLoading = false;

  // Form data
  let subjectTemplate = '';
  let bodyTemplate = '';
  let availablePlaceholders = [];
  let defaultSubject = '';
  let defaultBody = '';

  // Preview data
  let previewSubject = '';
  let previewBody = '';
  let previewInvoiceId = null;
  let invoices = [];

  // Debounce timer for preview
  let previewTimeout;

  onMount(async () => {
    await Promise.all([loadTemplates(), loadInvoices()]);
  });

  async function loadTemplates() {
    loading = true;
    try {
      const data = await emailApi.getTemplates();
      subjectTemplate = data.email_subject_template || '';
      bodyTemplate = data.email_body_template || '';
      availablePlaceholders = data.available_placeholders || [];
      defaultSubject = data.default_subject || '{document_type} {invoice_number}';
      defaultBody = data.default_body || '';
    } catch (error) {
      toast.error('Failed to load email templates');
    } finally {
      loading = false;
    }
  }

  async function loadInvoices() {
    try {
      const data = await invoicesApi.list({ limit: 10 });
      invoices = data;
      if (data.length > 0) {
        previewInvoiceId = data[0].id;
        await updatePreview();
      }
    } catch (error) {
      // Silently fail - preview is optional
    }
  }

  async function saveTemplates() {
    saving = true;
    try {
      await emailApi.updateTemplates({
        email_subject_template: subjectTemplate || null,
        email_body_template: bodyTemplate || null,
      });
      toast.success('Email templates saved');
    } catch (error) {
      toast.error('Failed to save templates');
    } finally {
      saving = false;
    }
  }

  async function updatePreview() {
    if (!previewInvoiceId) return;

    previewLoading = true;
    try {
      const data = await emailApi.previewEmail(previewInvoiceId, {
        subject_template: subjectTemplate || null,
        body_template: bodyTemplate || null,
      });
      previewSubject = data.subject;
      previewBody = data.body;
    } catch (error) {
      // Silently fail
    } finally {
      previewLoading = false;
    }
  }

  function schedulePreviewUpdate() {
    clearTimeout(previewTimeout);
    previewTimeout = setTimeout(updatePreview, 500);
  }

  function insertPlaceholder(placeholder) {
    // Insert at cursor position in body template (simple append for now)
    bodyTemplate = bodyTemplate + placeholder;
    schedulePreviewUpdate();
  }

  function resetToDefaults() {
    subjectTemplate = '';
    bodyTemplate = '';
    schedulePreviewUpdate();
  }

  $: if (subjectTemplate !== undefined || bodyTemplate !== undefined) {
    schedulePreviewUpdate();
  }
</script>

<Header title="Email Templates" />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <div class="page-header">
      <div>
        <h1>Email Templates</h1>
        <p class="page-subtitle">Customize the default email subject and body for invoice emails</p>
      </div>
      <a href="/settings" class="btn btn-ghost">
        <Icon name="chevron-left" size="sm" />
        Back to Settings
      </a>
    </div>

    <div class="templates-layout">
      <!-- Editor Panel -->
      <div class="editor-panel">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Templates</h3>
            <button class="btn btn-ghost btn-sm" on:click={resetToDefaults}>
              <Icon name="refresh" size="sm" />
              Reset to Defaults
            </button>
          </div>

          <div class="form-group">
            <label class="form-label" for="subject">Subject Template</label>
            <input
              type="text"
              id="subject"
              class="input"
              bind:value={subjectTemplate}
              on:input={schedulePreviewUpdate}
              placeholder={defaultSubject}
            />
            <p class="form-hint">Leave empty to use default: <code>{defaultSubject}</code></p>
          </div>

          <div class="form-group">
            <label class="form-label" for="body">Body Template</label>
            <textarea
              id="body"
              class="input textarea"
              bind:value={bodyTemplate}
              on:input={schedulePreviewUpdate}
              placeholder={defaultBody}
              rows="12"
            ></textarea>
            <p class="form-hint">Leave empty to use the default template</p>
          </div>

          <div class="form-actions">
            <button class="btn btn-primary" on:click={saveTemplates} disabled={saving}>
              {#if saving}
                <span class="spinner-sm"></span>
                Saving...
              {:else}
                <Icon name="check" size="sm" />
                Save Templates
              {/if}
            </button>
          </div>
        </div>

        <!-- Placeholders Reference -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Available Placeholders</h3>
          </div>
          <p class="text-secondary mb-3">Click a placeholder to insert it into the body template:</p>
          <div class="placeholders-grid">
            {#each availablePlaceholders as placeholder}
              <button
                class="placeholder-chip"
                on:click={() => insertPlaceholder(placeholder)}
                title="Click to insert"
              >
                {placeholder}
              </button>
            {/each}
          </div>
          <div class="placeholder-descriptions">
            <dl>
              <dt><code>{'{invoice_number}'}</code></dt>
              <dd>The invoice or quote number (e.g., INV-20250119-1)</dd>

              <dt><code>{'{document_type}'}</code></dt>
              <dd>"Invoice" or "Quote"</dd>

              <dt><code>{'{document_type_lower}'}</code></dt>
              <dd>"invoice" or "quote" (lowercase)</dd>

              <dt><code>{'{client_name}'}</code></dt>
              <dd>Client's contact name</dd>

              <dt><code>{'{client_business_name}'}</code></dt>
              <dd>Client's business name</dd>

              <dt><code>{'{total}'}</code> / <code>{'{amount}'}</code></dt>
              <dd>Formatted total amount (e.g., $1,234.56)</dd>

              <dt><code>{'{due_date}'}</code></dt>
              <dd>Due date formatted as "Month DD, YYYY"</dd>

              <dt><code>{'{issue_date}'}</code></dt>
              <dd>Issue date formatted as "Month DD, YYYY"</dd>

              <dt><code>{'{your_name}'}</code></dt>
              <dd>Your name from business profile</dd>

              <dt><code>{'{business_name}'}</code></dt>
              <dd>Your business name from profile</dd>
            </dl>
          </div>
        </div>
      </div>

      <!-- Preview Panel -->
      <div class="preview-panel">
        <div class="card sticky">
          <div class="card-header">
            <h3 class="card-title">Preview</h3>
            {#if invoices.length > 0}
              <select
                class="preview-select"
                bind:value={previewInvoiceId}
                on:change={updatePreview}
              >
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
              <p>No invoices available for preview</p>
              <p class="text-secondary">Create an invoice first to see the email preview</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 1400px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
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
    margin: var(--space-1) 0 0 0;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .templates-layout {
    display: grid;
    grid-template-columns: 1fr 400px;
    gap: var(--space-6);
    align-items: start;
  }

  .card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
  }

  .card + .card {
    margin-top: var(--space-6);
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-4);
  }

  .card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
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

  .textarea {
    resize: vertical;
    font-family: var(--font-mono);
    line-height: 1.5;
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  .form-hint code {
    background: var(--color-bg-sunken);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.875em;
  }

  .form-actions {
    display: flex;
    gap: var(--space-3);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
    margin-top: var(--space-4);
  }

  .text-secondary {
    color: var(--color-text-secondary);
  }

  .mb-3 {
    margin-bottom: var(--space-3);
  }

  .placeholders-grid {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-bottom: var(--space-4);
  }

  .placeholder-chip {
    padding: var(--space-1) var(--space-2);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--color-primary);
    cursor: pointer;
    transition: all 0.15s;
  }

  .placeholder-chip:hover {
    background: var(--color-primary-light);
    border-color: var(--color-primary);
  }

  .placeholder-descriptions {
    border-top: 1px solid var(--color-border-light);
    padding-top: var(--space-4);
    margin-top: var(--space-4);
  }

  .placeholder-descriptions dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--space-2) var(--space-4);
    font-size: 0.8125rem;
  }

  .placeholder-descriptions dt {
    color: var(--color-text);
  }

  .placeholder-descriptions dt code {
    background: var(--color-bg-sunken);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.875em;
  }

  .placeholder-descriptions dd {
    color: var(--color-text-secondary);
    margin: 0;
  }

  .sticky {
    position: sticky;
    top: var(--space-4);
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
    .templates-layout {
      grid-template-columns: 1fr;
    }

    .preview-panel {
      order: -1;
    }

    .sticky {
      position: static;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .page-header {
      flex-direction: column;
      align-items: stretch;
    }

    .placeholder-descriptions dl {
      grid-template-columns: 1fr;
    }

    .placeholder-descriptions dt {
      margin-top: var(--space-2);
    }
  }
</style>
