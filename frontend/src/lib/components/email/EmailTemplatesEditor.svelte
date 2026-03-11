<script>
  import Icon from '$lib/components/Icons.svelte';
  import { placeholderDescriptions } from '$lib/email/templates';

  export let subjectTemplate = '';
  export let bodyTemplate = '';
  export let availablePlaceholders = [];
  export let saving = false;
  export let resetToDefaults;
  export let saveTemplates;
  export let schedulePreviewUpdate;
  export let insertPlaceholder;
</script>

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
      <input type="text" id="subject" class="input" bind:value={subjectTemplate} on:input={schedulePreviewUpdate} />
      <p class="form-hint">Use placeholders like <code>{'{document_type}'}</code> to insert dynamic content</p>
    </div>

    <div class="form-group">
      <label class="form-label" for="body">Body Template</label>
      <textarea id="body" class="input textarea" bind:value={bodyTemplate} on:input={schedulePreviewUpdate} rows="12"></textarea>
      <p class="form-hint">Customize the email body sent with invoices. Click placeholders below to insert them.</p>
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

  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Available Placeholders</h3>
    </div>
    <p class="text-secondary mb-3">Click a placeholder to insert it into the body template:</p>
    <div class="placeholders-grid">
      {#each availablePlaceholders as placeholder}
        <button class="placeholder-chip" on:click={() => insertPlaceholder(placeholder)} title="Click to insert">
          {placeholder}
        </button>
      {/each}
    </div>
    <div class="placeholder-descriptions">
      <dl>
        {#each placeholderDescriptions as placeholder}
          <dt><code>{placeholder.code}</code></dt>
          <dd>{placeholder.description}</dd>
        {/each}
      </dl>
    </div>
  </div>
</div>

<style>
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

  .form-hint code,
  .placeholder-descriptions dt code {
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

  .placeholder-descriptions dd {
    color: var(--color-text-secondary);
    margin: 0;
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

  @media (max-width: 768px) {
    .placeholder-descriptions dl {
      grid-template-columns: 1fr;
    }

    .placeholder-descriptions dt {
      margin-top: var(--space-2);
    }
  }
</style>
