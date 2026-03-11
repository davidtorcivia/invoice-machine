<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let open = false;
  export let creatingBackup = false;
  export let createBackup;
  export let backupEnabled = true;
  export let backupRetentionDays = 30;
  export let backupS3Enabled = false;
  export let backupS3EndpointUrl = '';
  export let backupS3AccessKeyId = '';
  export let backupS3SecretAccessKey = '';
  export let backupS3Bucket = '';
  export let backupS3Region = '';
  export let backupS3Prefix = 'invoice-machine-backups';
  export let testingS3 = false;
  export let testS3Connection;
  export let saveBackupSettings;
  export let loadingBackups = false;
  export let backups = [];
  export let restoringBackup = null;
  export let openRestoreModal;
  export let openDeleteBackupModal;
  export let formatBytes;
  export let formatDate;
  export let downloadBackupHref;
</script>

<CollapsibleSection title="Backup & Restore" subtitle="Manage your data backups" icon="download" bind:open={open}>
  <div class="section-header-actions">
    <button
      type="button"
      class="btn btn-secondary btn-sm"
      on:click={createBackup}
      disabled={creatingBackup}
    >
      <Icon name="plus" size="sm" />
      {creatingBackup ? 'Creating...' : 'Create Backup'}
    </button>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={backupEnabled} />
        <span>Enable automatic daily backups</span>
      </label>
    </div>

    <div class="form-group">
      <label for="backup-retention" class="label">Retention (days)</label>
      <input
        id="backup-retention"
        type="number"
        class="input"
        min="1"
        max="365"
        bind:value={backupRetentionDays}
      />
    </div>
  </div>

  <div class="s3-section">
    <label class="checkbox-label mb-3">
      <input type="checkbox" bind:checked={backupS3Enabled} />
      <span>Upload backups to S3-compatible storage</span>
    </label>

    {#if backupS3Enabled}
      <div class="s3-fields">
        <div class="form-group">
          <label for="s3-endpoint" class="label">Endpoint URL (optional)</label>
          <input
            id="s3-endpoint"
            type="url"
            class="input"
            placeholder="https://s3.amazonaws.com or Backblaze/MinIO URL"
            bind:value={backupS3EndpointUrl}
          />
          <p class="form-hint">Leave empty for AWS S3, or enter custom endpoint for Backblaze B2, MinIO, etc.</p>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="s3-access-key" class="label">Access Key ID</label>
            <input
              id="s3-access-key"
              type="text"
              class="input"
              placeholder="AKIAIOSFODNN7EXAMPLE"
              bind:value={backupS3AccessKeyId}
            />
          </div>

          <div class="form-group">
            <label for="s3-secret-key" class="label">Secret Access Key</label>
            <input
              id="s3-secret-key"
              type="password"
              class="input"
              placeholder="Enter secret key"
              bind:value={backupS3SecretAccessKey}
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="s3-bucket" class="label">Bucket Name</label>
            <input
              id="s3-bucket"
              type="text"
              class="input"
              placeholder="my-backup-bucket"
              bind:value={backupS3Bucket}
            />
          </div>

          <div class="form-group">
            <label for="s3-region" class="label">Region</label>
            <input
              id="s3-region"
              type="text"
              class="input"
              placeholder="us-east-1"
              bind:value={backupS3Region}
            />
          </div>
        </div>

        <div class="form-group">
          <label for="s3-prefix" class="label">Path Prefix</label>
          <input
            id="s3-prefix"
            type="text"
            class="input"
            placeholder="invoice-machine-backups"
            bind:value={backupS3Prefix}
          />
        </div>

        <button
          type="button"
          class="btn btn-secondary btn-sm"
          on:click={testS3Connection}
          disabled={testingS3}
        >
          {testingS3 ? 'Testing...' : 'Test S3 Connection'}
        </button>
      </div>
    {/if}
  </div>

  <div class="backup-actions mt-4">
    <button type="button" class="btn btn-secondary" on:click={saveBackupSettings}>
      <Icon name="check" size="sm" />
      Save Backup Settings
    </button>
  </div>

  <div class="backup-list mt-4">
    <h4 class="backup-list-title">Available Backups</h4>

    {#if loadingBackups}
      <div class="loading-container">
        <div class="spinner"></div>
      </div>
    {:else if backups.length === 0}
      <p class="text-secondary">No backups yet. Create one using the button above.</p>
    {:else}
      <div class="backup-items">
        {#each backups as backup}
          <div class="backup-item">
            <div class="backup-info">
              <span class="backup-filename">{backup.filename}</span>
              <span class="backup-meta">
                {formatBytes(backup.size_bytes)} | {formatDate(backup.created_at)}
                {#if backup.location === 's3'}
                  <span class="backup-location">S3</span>
                {/if}
              </span>
            </div>
            <div class="backup-item-actions">
              {#if backup.location === 'local'}
                <a
                  href={downloadBackupHref(backup.filename)}
                  class="btn btn-ghost btn-icon btn-sm"
                  title="Download"
                  download
                >
                  <Icon name="download" size="sm" />
                </a>
              {/if}
              <button
                type="button"
                class="btn btn-ghost btn-icon btn-sm"
                on:click={() => openRestoreModal(backup)}
                title="Restore"
                disabled={restoringBackup === backup.filename}
              >
                <Icon name="refresh" size="sm" />
              </button>
              {#if backup.location === 'local'}
                <button
                  type="button"
                  class="btn btn-ghost btn-icon btn-sm"
                  on:click={() => openDeleteBackupModal(backup)}
                  title="Delete"
                >
                  <Icon name="trash" size="sm" />
                </button>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</CollapsibleSection>

<style>
  .section-header-actions {
    display: flex;
    justify-content: flex-end;
    margin-bottom: var(--space-4);
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 500;
  }

  .checkbox-label input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: pointer;
    accent-color: var(--color-primary);
  }

  .s3-section {
    margin-top: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
  }

  .s3-fields {
    margin-top: var(--space-3);
    padding: var(--space-4);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
  }

  .mb-3 {
    margin-bottom: var(--space-3);
  }

  .backup-actions {
    display: flex;
    gap: var(--space-2);
  }

  .backup-list {
    border-top: 1px solid var(--color-border-light);
    padding-top: var(--space-4);
  }

  .backup-list-title {
    font-size: 0.9375rem;
    font-weight: 600;
    margin-bottom: var(--space-3);
    color: var(--color-text);
  }

  .backup-items {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .backup-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    gap: var(--space-3);
  }

  .backup-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
    flex: 1;
  }

  .backup-filename {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .backup-meta {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .backup-location {
    display: inline-block;
    padding: 0.1em 0.4em;
    background: var(--color-primary-light);
    color: var(--color-primary);
    border-radius: var(--radius-sm);
    font-weight: 500;
    font-size: 0.6875rem;
    text-transform: uppercase;
    margin-left: var(--space-2);
  }

  .backup-item-actions {
    display: flex;
    gap: var(--space-1);
    flex-shrink: 0;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .text-secondary {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }
</style>
