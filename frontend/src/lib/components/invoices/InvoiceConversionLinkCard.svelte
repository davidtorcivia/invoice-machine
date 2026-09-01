<script>
  let { invoice } = $props();
</script>

{#if invoice.converted_to_invoice_id}
  <div class="card">
    <div class="card-body">
      <p class="link-hint">
        This quote was converted to
        <a href="/invoices/{invoice.converted_to_invoice_id}">an invoice</a>.
      </p>
    </div>
  </div>
{:else if invoice.converted_from_invoice_id}
  <div class="card">
    <div class="card-body">
      <p class="link-hint">
        Created from
        <a href="/invoices/{invoice.converted_from_invoice_id}">a quote</a>.
      </p>
    </div>
  </div>
{/if}

<style>
  .link-hint {
    margin: 0 0 0.75rem;
    color: var(--color-text-muted);
    font-size: 0.85rem;
    line-height: 1.5;
  }
</style>
