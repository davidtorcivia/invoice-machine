<script>
  import Icon from '$lib/components/Icons.svelte';

  export let show = false;
  export let editingMethod = null;
  export let newMethodName = '';
  export let newMethodInstructions = '';
  export let closePaymentMethodModal;
  export let savePaymentMethod;

  function handleModalKeydown(event) {
    if (event.key === 'Escape') {
      closePaymentMethodModal();
    }
  }
</script>

{#if show}
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={handleModalKeydown}>
    <button type="button" class="modal-backdrop" aria-label="Close payment method dialog" on:click={closePaymentMethodModal}></button>
    <div class="modal" role="dialog" aria-modal="true" tabindex="-1">
      <div class="modal-header">
        <h2 class="modal-title">{editingMethod ? 'Edit Payment Method' : 'Add Payment Method'}</h2>
        <button class="btn btn-ghost btn-icon btn-sm" on:click={closePaymentMethodModal}>
          <Icon name="x" size="md" />
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="method-name" class="label">Method Name *</label>
          <input
            id="method-name"
            type="text"
            class="input"
            placeholder="e.g., Bank Transfer (ACH), Venmo, Zelle"
            bind:value={newMethodName}
          />
        </div>
        <div class="form-group">
          <label for="method-instructions" class="label">Payment Details</label>
          <textarea
            id="method-instructions"
            class="textarea"
            rows="5"
            placeholder="Enter the payment details your clients will need, e.g.:&#10;Bank: Example Bank&#10;Account: 123456789&#10;Routing: 987654321"
            bind:value={newMethodInstructions}
          ></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" on:click={closePaymentMethodModal}>Cancel</button>
        <button class="btn btn-primary" on:click={savePaymentMethod}>
          {editingMethod ? 'Save Changes' : 'Add Method'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }
</style>
