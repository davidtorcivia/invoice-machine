<script>
  /** @typedef {{ id: string, name: string, instructions?: string }} PaymentMethod */

  /** @type {PaymentMethod[]} */
  export let availablePaymentMethods = [];
  /** @type {string[]} */
  export let selectedPaymentMethods = [];
  export let showPaymentInstructions = true;
  export let selectionHint = 'Select payment methods to include on the PDF.';

  /**
   * @param {Event} event
   * @returns {HTMLInputElement}
   */
  function getInputTarget(event) {
    return /** @type {HTMLInputElement} */ (event.currentTarget);
  }

  function toggleSelectedMethod(methodId, checked) {
    selectedPaymentMethods = checked
      ? [...selectedPaymentMethods, methodId]
      : selectedPaymentMethods.filter((id) => id !== methodId);
  }
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Payment Instructions</h3>
  </div>

  {#if availablePaymentMethods.length > 0}
    <p class="form-hint intro-hint">{selectionHint}</p>
    <div class="payment-methods-list">
      {#each availablePaymentMethods as method}
        <label class="payment-method-option">
          <input
            type="checkbox"
            checked={selectedPaymentMethods.includes(method.id)}
            on:change={(event) => toggleSelectedMethod(method.id, getInputTarget(event).checked)}
          />
          <div class="payment-method-info">
            <span class="payment-method-name">{method.name}</span>
            {#if method.instructions}
              <span class="payment-method-preview">{method.instructions.substring(0, 50)}{method.instructions.length > 50 ? '...' : ''}</span>
            {/if}
          </div>
        </label>
      {/each}
    </div>
    {#if selectedPaymentMethods.length > 0}
      <p class="form-hint selected-count">
        {selectedPaymentMethods.length} payment method{selectedPaymentMethods.length !== 1 ? 's' : ''} will be shown on the PDF.
      </p>
    {/if}
  {:else}
    <label class="checkbox-label">
      <input type="checkbox" bind:checked={showPaymentInstructions} />
      <span>Include Payment Instructions</span>
    </label>
    <p class="form-hint">
      Configure payment methods in <a href="/settings" class="link">Settings</a> to select which ones to show on invoices.
    </p>
  {/if}
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

  .payment-methods-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .payment-method-option {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-3);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .payment-method-option:hover {
    border-color: var(--color-border-dark);
    background: var(--color-bg-hover);
  }

  .payment-method-option:has(input:checked) {
    border-color: var(--color-primary);
    background: color-mix(in srgb, var(--color-primary) 5%, var(--color-bg-sunken));
  }

  .payment-method-option input[type='checkbox'] {
    width: 18px;
    height: 18px;
    margin-top: 2px;
    accent-color: var(--color-primary);
    flex-shrink: 0;
  }

  .payment-method-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .payment-method-name {
    font-weight: 500;
    color: var(--color-text);
  }

  .payment-method-preview {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-2);
  }

  .intro-hint {
    margin-top: 0;
    margin-bottom: var(--space-3);
  }

  .selected-count {
    margin-top: var(--space-3);
    color: var(--color-primary);
    font-weight: 500;
  }

  .link {
    color: var(--color-primary);
    text-decoration: none;
  }

  .link:hover {
    text-decoration: underline;
  }
</style>
