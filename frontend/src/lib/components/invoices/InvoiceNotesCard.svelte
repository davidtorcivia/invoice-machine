<script>
  import Icon from '$lib/components/Icons.svelte';

  export let useDefaultNotes = false;
  export let defaultNotesText = '';
  export let notes = '';
  export let placeholder = 'Payment terms, thank you message, etc.';

  function removeDefaultNotes() {
    useDefaultNotes = false;
    notes = '';
  }

  function restoreDefaultNotes() {
    useDefaultNotes = true;
    notes = '';
  }
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Notes</h3>
  </div>

  {#if useDefaultNotes && defaultNotesText}
    <div class="default-notes-display">
      <div class="default-notes-header">
        <span class="default-notes-label">Using default notes from Settings</span>
        <button
          type="button"
          class="btn btn-ghost btn-sm"
          on:click={removeDefaultNotes}
        >
          <Icon name="x" size="sm" />
          Remove
        </button>
      </div>
      <div class="default-notes-content">
        {defaultNotesText}
      </div>
    </div>
  {:else}
    <textarea
      class="textarea"
      rows="3"
      {placeholder}
      bind:value={notes}
    ></textarea>
    {#if defaultNotesText && !useDefaultNotes}
      <button
        type="button"
        class="btn btn-ghost btn-sm mt-2"
        on:click={restoreDefaultNotes}
      >
        <Icon name="refresh" size="sm" />
        Use default notes
      </button>
    {/if}
  {/if}
</div>

<style>
  .default-notes-display {
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .default-notes-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-hover);
    border-bottom: 1px solid var(--color-border);
  }

  .default-notes-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }

  .default-notes-content {
    padding: var(--space-3) var(--space-4);
    font-size: 0.9375rem;
    color: var(--color-text);
    white-space: pre-wrap;
    line-height: 1.6;
  }

  .mt-2 {
    margin-top: var(--space-2);
  }
</style>
