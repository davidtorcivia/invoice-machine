<script>
  export let invoice = {};
  export let documentType = 'invoice';
  export let issueDate = '';
  export let dueDate = '';
  export let paymentTermsDays = 30;
  export let status = 'draft';
  export let clientReference = '';
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">{documentType === 'quote' ? 'Quote' : 'Invoice'} Details</h3>
  </div>

  <div class="form-group invoice-number-group">
    <div class="label">{documentType === 'quote' ? 'Quote' : 'Invoice'} Number</div>
    <div class="invoice-number-display">
      <span class="invoice-number-value">{invoice.invoice_number || ''}</span>
      <span class="invoice-number-hint">Currency: {invoice.currency_code || 'USD'}</span>
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="issue-date" class="label">Issue Date</label>
      <input id="issue-date" type="date" class="input" bind:value={issueDate} />
      <p class="form-hint">Changing the issue date may update the invoice number.</p>
    </div>

    <div class="form-group">
      <label for="due-date" class="label">Due Date</label>
      <input id="due-date" type="date" class="input" bind:value={dueDate} />
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="terms" class="label">Payment Terms (days)</label>
      <input id="terms" type="number" class="input" min="0" bind:value={paymentTermsDays} />
    </div>

    <div class="form-group">
      <label for="status" class="label">Status</label>
      <select id="status" class="select" bind:value={status}>
        <option value="draft">Draft</option>
        <option value="sent">Sent</option>
        <option value="paid">Paid</option>
        <option value="overdue">Overdue</option>
        <option value="cancelled">Cancelled</option>
      </select>
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="client-ref" class="label">Client Reference / PO Number</label>
      <input id="client-ref" type="text" class="input" placeholder="PO-12345" bind:value={clientReference} />
    </div>
  </div>
</div>

<style>
  .invoice-number-group {
    margin-bottom: var(--space-4);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  .invoice-number-display {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .invoice-number-value {
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--color-text);
  }

  .invoice-number-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-left: auto;
  }
</style>
