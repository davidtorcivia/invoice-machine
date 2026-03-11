<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let invoiceId = '';
  export let invoice = {};
  export let documentLabel = 'Invoice';
  export let generatingPdf = false;

  const dispatch = createEventDispatcher();
</script>

<div class="page-header">
  <div class="page-header-text">
    <h1>{documentLabel} #{invoice.invoice_number}</h1>
    <p class="page-subtitle">{invoice.client_business || invoice.client_name || ''}</p>
  </div>
  <div class="page-actions">
    <a href="/invoices/{invoiceId}/edit" class="btn btn-secondary">
      <Icon name="pencil" size="sm" />
      Edit
    </a>
    <button class="btn btn-secondary" on:click={() => dispatch('generatepdf')} disabled={generatingPdf}>
      <Icon name="refresh" size="sm" />
      {generatingPdf ? 'Generating...' : 'Generate PDF'}
    </button>
    <button class="btn btn-primary" on:click={() => dispatch('downloadpdf')}>
      <Icon name="download" size="sm" />
      Download PDF
    </button>
    <button class="btn btn-secondary" on:click={() => dispatch('sendemail')}>
      <Icon name="send" size="sm" />
      Send Email
    </button>
  </div>
</div>

<style>
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-6);
    gap: var(--space-4);
    flex-wrap: wrap;
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

  .page-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  @media (max-width: 768px) {
    .page-header {
      flex-direction: column;
      align-items: stretch;
      gap: var(--space-3);
    }

    .page-actions {
      flex-wrap: wrap;
    }

    .page-actions .btn {
      flex: 1;
      min-width: fit-content;
    }
  }

  @media (max-width: 480px) {
    .page-header h1 {
      font-size: 1.25rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
    }
  }
</style>
