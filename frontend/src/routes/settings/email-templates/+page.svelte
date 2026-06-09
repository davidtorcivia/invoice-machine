<script>
  import { onMount } from 'svelte';
  import { emailApi, invoicesApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import EmailTemplatesEditor from '$lib/components/email/EmailTemplatesEditor.svelte';
  import EmailTemplatePreviewCard from '$lib/components/email/EmailTemplatePreviewCard.svelte';

  let loading = true;
  let saving = false;
  let previewLoading = false;
  let subjectTemplate = '';
  let bodyTemplate = '';
  let availablePlaceholders = [];
  let defaultSubject = '';
  let defaultBody = '';
  let previewSubject = '';
  let previewBody = '';
  let previewInvoiceId = null;
  let invoices = [];
  let previewTimeout;

  onMount(async () => {
    await Promise.all([loadTemplates(), loadInvoices()]);
  });

  async function loadTemplates() {
    loading = true;
    try {
      const data = await emailApi.getTemplates();
      availablePlaceholders = data.available_placeholders || [];
      defaultSubject = data.default_subject || '{document_type} {invoice_number}';
      defaultBody = data.default_body || '';
      subjectTemplate = data.email_subject_template ?? defaultSubject;
      bodyTemplate = data.email_body_template ?? defaultBody;
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
      // Preview is optional.
    }
  }

  async function saveTemplates() {
    saving = true;
    try {
      await emailApi.updateTemplates({
        email_subject_template: subjectTemplate || null,
        email_body_template: bodyTemplate || null
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
        body_template: bodyTemplate || null
      });
      previewSubject = data.subject;
      previewBody = data.body;
    } catch (error) {
      // Preview is optional.
    } finally {
      previewLoading = false;
    }
  }

  function schedulePreviewUpdate() {
    clearTimeout(previewTimeout);
    previewTimeout = setTimeout(updatePreview, 500);
  }

  function insertPlaceholder(placeholder) {
    bodyTemplate += placeholder;
    schedulePreviewUpdate();
  }

  function resetToDefaults() {
    subjectTemplate = defaultSubject;
    bodyTemplate = defaultBody;
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
        <Icon name="chevronLeft" size="sm" />
        Back to Settings
      </a>
    </div>

    <div class="templates-layout">
      <EmailTemplatesEditor
        bind:subjectTemplate
        bind:bodyTemplate
        {availablePlaceholders}
        {saving}
        {resetToDefaults}
        {saveTemplates}
        {schedulePreviewUpdate}
        {insertPlaceholder}
      />

      <EmailTemplatePreviewCard
        {invoices}
        bind:previewInvoiceId
        {previewLoading}
        {previewSubject}
        {previewBody}
        {updatePreview}
      />
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

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 1024px) {
    .templates-layout {
      grid-template-columns: 1fr;
    }

    :global(.preview-panel) {
      order: -1;
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
  }
</style>
