<script lang="ts">
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import { profileApi } from '$lib/api';
  import { toast } from '$lib/stores';

  interface Props {
    open?: boolean;
    logoPreview?: any;
  }

  let { open = $bindable(false), logoPreview = $bindable(null) }: Props = $props();

  let logoUploading = $state(false);
  let showDeleteModal = $state(false);
  let deleting = $state(false);

  async function handleLogoSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be less than 5MB');
      return;
    }

    logoUploading = true;

    try {
      const result = await profileApi.uploadLogo(file);
      logoPreview = `/api/profile/logo/${result.logo_path}`;
      toast.success('Logo uploaded successfully');
    } catch (error) {
      toast.error('Failed to upload logo');
    } finally {
      logoUploading = false;
      event.target.value = '';
    }
  }

  async function deleteLogo() {
    deleting = true;
    try {
      await profileApi.deleteLogo();
      logoPreview = null;
      toast.success('Logo deleted');
      showDeleteModal = false;
    } catch (error) {
      toast.error('Failed to delete logo');
    } finally {
      deleting = false;
    }
  }
</script>

<CollapsibleSection title="Logo" subtitle="Company logo for invoices" icon="image" bind:open={open}>
  <div class="logo-section">
    <div class="logo-preview" class:has-logo={logoPreview} class:uploading={logoUploading}>
      {#if logoUploading}
        <div class="upload-progress">
          <div class="progress-bar">
            <!-- Indeterminate: real upload progress isn't tracked. -->
            <div class="progress-fill indeterminate"></div>
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
            onchange={handleLogoSelect}
            disabled={logoUploading}
            style="display: none"
          />
        </label>

        {#if logoPreview && !logoUploading}
          <button class="btn btn-ghost btn-danger-text" onclick={() => (showDeleteModal = true)}>
            <Icon name="trash" size="sm" />
            Delete
          </button>
        {/if}
      </div>
    </div>
  </div>
</CollapsibleSection>

<ConfirmModal
  show={showDeleteModal}
  title="Delete Logo"
  message="This will remove your logo from all invoices. This action cannot be undone."
  confirmText={deleting ? 'Deleting...' : 'Delete Logo'}
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deleting}
  onConfirm={deleteLogo}
  onCancel={() => (showDeleteModal = false)}
/>

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

  .progress-fill.indeterminate {
    width: 40%;
    border-radius: var(--radius-full);
    animation: indeterminate 1.1s ease-in-out infinite;
  }

  @keyframes indeterminate {
    0% { margin-left: -40%; }
    100% { margin-left: 100%; }
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
