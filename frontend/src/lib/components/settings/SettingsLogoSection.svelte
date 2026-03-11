<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let open = false;
  export let logoPreview = null;
  export let logoUploading = false;
  export let uploadProgress = 0;
  export let handleLogoSelect;
  export let openDeleteLogoModal;
</script>

<CollapsibleSection title="Logo" subtitle="Company logo for invoices" icon="image" bind:open={open}>
  <div class="logo-section">
    <div class="logo-preview" class:has-logo={logoPreview} class:uploading={logoUploading}>
      {#if logoUploading}
        <div class="upload-progress">
          <div class="progress-bar">
            <div class="progress-fill" style="width: {Math.min(uploadProgress, 100)}%"></div>
          </div>
          <span class="progress-text">Uploading...</span>
        </div>
      {:else if logoPreview}
        <img src={logoPreview} alt="Logo" />
      {:else}
        <div class="logo-placeholder">
          <Icon name="image" size="lg" />
          <span>Your Logo</span>
        </div>
      {/if}
    </div>

    <div class="logo-controls">
      <p class="logo-hint">Upload your company logo. It will appear on invoices and PDFs.</p>
      <div class="logo-buttons">
        <label class="btn btn-secondary" class:disabled={logoUploading}>
          <Icon name="upload" size="sm" />
          {logoPreview ? 'Change Logo' : 'Upload Logo'}
          <input
            type="file"
            accept="image/*"
            on:change={handleLogoSelect}
            disabled={logoUploading}
            style="display: none"
          />
        </label>

        {#if logoPreview && !logoUploading}
          <button class="btn btn-ghost btn-danger-text" on:click={openDeleteLogoModal}>
            <Icon name="trash" size="sm" />
            Delete
          </button>
        {/if}
      </div>
    </div>
  </div>
</CollapsibleSection>

<style>
  .logo-section {
    display: flex;
    gap: var(--space-6);
    align-items: flex-start;
  }

  .logo-preview {
    width: 160px;
    height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-sunken);
    border: 2px dashed var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    flex-shrink: 0;
    position: relative;
  }

  .logo-preview.has-logo {
    border-style: solid;
    background: var(--color-bg);
  }

  .logo-preview.uploading {
    border-color: var(--color-primary);
    background: var(--color-primary-light);
  }

  .logo-preview img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .logo-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-text-tertiary);
    font-size: 0.8125rem;
  }

  .upload-progress {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    width: 80%;
  }

  .progress-bar {
    width: 100%;
    height: 4px;
    background: var(--color-bg);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--color-primary);
    transition: width 0.1s ease;
  }

  .progress-text {
    font-size: 0.75rem;
    color: var(--color-primary);
    font-weight: 500;
  }

  .logo-controls {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .logo-hint {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    line-height: 1.5;
  }

  .logo-buttons {
    display: flex;
    gap: var(--space-2);
  }

  .btn.disabled {
    opacity: 0.5;
    pointer-events: none;
  }

  .btn-danger-text {
    color: var(--color-danger);
  }

  .btn-danger-text:hover:not(:disabled) {
    background: var(--color-danger-light);
    color: var(--color-danger);
  }

  @media (max-width: 768px) {
    .logo-section {
      flex-direction: column;
    }

    .logo-preview {
      width: 100%;
      max-width: 200px;
    }

    .logo-buttons {
      flex-direction: column;
    }
  }
</style>
