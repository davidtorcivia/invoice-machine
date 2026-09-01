<script lang="ts">
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import SettingsBackupList from './SettingsBackupList.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import { backupsApi } from '$lib/api';
  import { toast } from '$lib/stores';

  interface Props {
    open?: boolean;
    backupEnabled?: boolean;
    backupRetentionDays?: number;
    backupS3Enabled?: boolean;
    backupS3EndpointUrl?: string;
    backupS3AccessKeyId?: string;
    backupS3SecretAccessKey?: string;
    backupS3Bucket?: string;
    backupS3Region?: string;
    backupS3Prefix?: string;
    testingS3?: boolean;
    testS3Connection: any;
  }

  let {
    open = $bindable(false),
    backupEnabled = $bindable(true),
    backupRetentionDays = $bindable(30),
    backupS3Enabled = $bindable(false),
    backupS3EndpointUrl = $bindable(''),
    backupS3AccessKeyId = $bindable(''),
    backupS3SecretAccessKey = $bindable(''),
    backupS3Bucket = $bindable(''),
    backupS3Region = $bindable(''),
    backupS3Prefix = $bindable('invoice-machine-backups'),
    testingS3 = false,
    testS3Connection
  }: Props = $props();

  let backups = $state<any[]>([]);
  let loadingBackups = $state(false);
  let creatingBackup = $state(false);
  // Restore and delete state lives above CollapsibleSection: collapsing the
  // section unmounts its children mid-request otherwise.
  let restoringBackup = $state<any>(null);
  let restoreTarget = $state<any>(null);
  let deleteTarget = $state<any>(null);
  let deletingBackup = $state(false);

  // Fetching lives here rather than in the list child: CollapsibleSection only
  // renders its children while expanded, so the child may not exist yet.
  export async function reloadBackups() {
    loadingBackups = true;
    try {
      backups = await backupsApi.list(backupS3Enabled);
    } catch (error) {
      backups = [];
    } finally {
      loadingBackups = false;
    }
  }

  async function restoreBackup() {
    if (!restoreTarget) return;
    restoringBackup = restoreTarget.filename;
    try {
      const result = await backupsApi.restore(restoreTarget.filename, restoreTarget.location === 's3');
      toast.success(result.message);
      restoreTarget = null;
    } catch (error) {
      toast.error(error.message || 'Failed to restore backup');
    } finally {
      restoringBackup = null;
    }
  }

  async function deleteBackup() {
    if (!deleteTarget) return;
    deletingBackup = true;
    try {
      await backupsApi.delete(deleteTarget.filename);
      toast.success('Backup deleted');
      await reloadBackups();
    } catch (error) {
      toast.error('Failed to delete backup');
    } finally {
      deletingBackup = false;
      deleteTarget = null;
    }
  }

  async function createBackup() {
    creatingBackup = true;
    try {
      const result = await backupsApi.create(true);
      toast.success(`Backup created: ${result.filename}`);
      await reloadBackups();
    } catch (error) {
      toast.error(error.message || 'Failed to create backup');
    } finally {
      creatingBackup = false;
    }
  }
</script>

<CollapsibleSection title="Backup & Restore" subtitle="Manage your data backups" icon="download" bind:open={open}>
  <div class="section-header-actions">
    <button
      type="button"
      class="btn btn-secondary btn-sm"
      onclick={createBackup}
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
          onclick={testS3Connection}
          disabled={testingS3}
        >
          {testingS3 ? 'Testing...' : 'Test S3 Connection'}
        </button>
        <p class="form-hint">Saves your backup settings before testing.</p>
      </div>
    {/if}
  </div>

  <SettingsBackupList
    {backups}
    loading={loadingBackups}
    {restoringBackup}
    onrestore={(backup) => (restoreTarget = backup)}
    ondelete={(backup) => (deleteTarget = backup)}
  />
</CollapsibleSection>

<ConfirmModal
  show={!!restoreTarget}
  title="Restore Backup"
  message={restoreTarget
    ? `This will overwrite your current database with ${restoreTarget.filename}. A pre-restore backup will be created automatically. The application will need to be restarted after restore.`
    : 'Restore this backup?'}
  confirmText={restoringBackup ? 'Restoring...' : 'Restore Backup'}
  cancelText="Cancel"
  variant="warning"
  icon="refresh"
  loading={!!restoringBackup}
  onConfirm={restoreBackup}
  onCancel={() => (restoreTarget = null)}
/>

<ConfirmModal
  show={!!deleteTarget}
  title="Delete Backup"
  message="Delete backup {deleteTarget?.filename}? This action cannot be undone."
  confirmText="Delete"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deletingBackup}
  onConfirm={deleteBackup}
  onCancel={() => (deleteTarget = null)}
/>

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

</style>
