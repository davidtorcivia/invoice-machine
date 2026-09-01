<script lang="ts">
  import Icon from '$lib/components/Icons.svelte';
  import { backupsApi } from '$lib/api';
  import { formatBackupBytes, formatBackupDate } from '$lib/settings/forms';

  interface Props {
    backups?: any[];
    loading?: boolean;
    restoringBackup?: any;
    onrestore: (backup: any) => void;
    ondelete: (backup: any) => void;
  }

  let { backups = [], loading = false, restoringBackup = null, onrestore, ondelete }: Props = $props();
</script>

<div class="backup-list mt-4">
  <h4 class="backup-list-title">Available Backups</h4>

  {#if loading}
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
              {formatBackupBytes(backup.size_bytes)} | {formatBackupDate(backup.created_at)}
              {#if backup.location === 's3'}
                <span class="backup-location">S3</span>
              {/if}
            </span>
          </div>
          <div class="backup-item-actions">
            {#if backup.location === 'local'}
              <a
                href={backupsApi.download(backup.filename)}
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
              onclick={() => onrestore(backup)}
              title="Restore"
              disabled={restoringBackup === backup.filename}
            >
              <Icon name="refresh" size="sm" />
            </button>
            {#if backup.location === 'local'}
              <button
                type="button"
                class="btn btn-ghost btn-icon btn-sm"
                onclick={() => ondelete(backup)}
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

<style>
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
