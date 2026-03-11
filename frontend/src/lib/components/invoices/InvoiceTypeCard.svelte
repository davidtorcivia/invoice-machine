<script>
  export let documentType = 'invoice';
  export let helpText = 'Quotes use a different number format (Q-YYYYMMDD-N) and show "Quote" instead of "Invoice" on the PDF.';
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Document Type</h3>
  </div>
  <label class="checkbox-label">
    <input type="checkbox" checked={documentType === 'quote'} on:change={(event) => documentType = event.currentTarget.checked ? 'quote' : 'invoice'} />
    <span>This is a Quote</span>
  </label>
  <p class="form-hint">{helpText}</p>
</div>

<style>
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 500;
  }

  .checkbox-label input[type='checkbox'] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }
</style>
