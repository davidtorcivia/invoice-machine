<script lang="ts">
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import { apiKeysApi } from '$lib/api';
  import { formatDate, toast } from '$lib/stores';

  interface ApiKey {
    id: number;
    kind: string;
    label: string;
    prefix: string | null;
    created_at: string | null;
    last_used_at: string | null;
  }

  interface Props {
    kind: string;
    keys: ApiKey[];
    placeholder: string;
    // Owned by the parent: this component is unmounted whenever its section is
    // collapsed, and the one-time plaintext cannot be fetched again.
    drafts: Record<string, string>;
    revealed: Record<number, string>;
    onchanged: () => Promise<void> | void;
  }

  let { kind, keys, placeholder, drafts, revealed, onchanged }: Props = $props();

  let busy = $state(false);
  let pending = $state<{ action: 'rotate' | 'revoke'; key: ApiKey } | null>(null);

  async function createKey() {
    const label = drafts[kind].trim();
    if (!label) {
      toast.error('Give the key a name first');
      return;
    }
    busy = true;
    try {
      const created = await apiKeysApi.create(kind, label);
      revealed[created.id] = created.key;
      drafts[kind] = '';
      await onchanged();
      toast.success('API key created');
    } catch {
      toast.error('Failed to create API key');
    } finally {
      busy = false;
    }
  }

  async function confirmPending() {
    if (!pending) return;
    const { action, key } = pending;
    busy = true;
    try {
      if (action === 'rotate') {
        const rotated = await apiKeysApi.rotate(key.id);
        revealed[key.id] = rotated.key;
        toast.success('API key rotated');
      } else {
        await apiKeysApi.remove(key.id);
        delete revealed[key.id];
        toast.success('API key revoked');
      }
      await onchanged();
      pending = null;
    } catch {
      toast.error(action === 'rotate' ? 'Failed to rotate key' : 'Failed to revoke key');
    } finally {
      busy = false;
    }
  }

  async function renameKey(key: ApiKey) {
    const label = window.prompt('Rename key', key.label)?.trim();
    if (!label || label === key.label) return;
    try {
      await apiKeysApi.rename(key.id, label);
      await onchanged();
    } catch {
      toast.error('Failed to rename key');
    }
  }

  async function copyKey(id: number) {
    if (!navigator.clipboard?.writeText) {
      toast.error('Clipboard is unavailable (requires HTTPS). Copy the key manually.');
      return;
    }
    try {
      await navigator.clipboard.writeText(revealed[id]);
      toast.success('API key copied to clipboard');
    } catch {
      toast.error('Could not copy to clipboard. Copy the key manually.');
    }
  }
</script>

{#if keys.length > 0}
  <div class="table-container">
    <table class="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Key</th>
          <th>Created</th>
          <th>Last used</th>
          <th class="text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {#each keys as key (key.id)}
          <tr>
            <td>
              <button type="button" class="btn btn-ghost btn-sm" disabled={busy} onclick={() => renameKey(key)} title="Rename" aria-label="Rename {key.label}">
                {key.label}
                <Icon name="pencil" size="sm" />
              </button>
            </td>
            <td><span class="font-mono key-prefix">{key.prefix ? `${key.prefix}…` : '—'}</span></td>
            <td class="text-secondary">{formatDate(key.created_at)}</td>
            <td class="text-secondary">{key.last_used_at ? formatDate(key.last_used_at) : 'never'}</td>
            <td class="text-right">
              <button type="button" class="btn btn-ghost btn-sm" disabled={busy} onclick={() => (pending = { action: 'rotate', key })}>
                <Icon name="refresh" size="sm" />
                Rotate
              </button>
              <button type="button" class="btn btn-ghost btn-sm btn-danger-text" disabled={busy} onclick={() => (pending = { action: 'revoke', key })}>
                <Icon name="trash" size="sm" />
                Revoke
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<div class="key-new">
  <input
    type="text"
    class="input"
    maxlength="100"
    placeholder={placeholder}
    bind:value={drafts[kind]}
    onkeydown={(event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        createKey();
      }
    }}
  />
  <button type="button" class="btn btn-primary" disabled={busy} onclick={createKey}>
    <Icon name="plus" size="sm" />
    New key
  </button>
</div>

{#each keys.filter((key) => revealed[key.id]) as key (key.id)}
  <div class="mcp-key-display">
    <label class="label" for="revealed-key-{key.id}">{key.label}</label>
    <div class="mcp-key-row">
      <input id="revealed-key-{key.id}" type="text" class="input" value={revealed[key.id]} readonly />
      <button type="button" class="btn btn-secondary" onclick={() => copyKey(key.id)}>
        <Icon name="copy" size="sm" />
        Copy
      </button>
    </div>
    <p class="form-hint">Shown once. Copy it now — it cannot be recovered.</p>
  </div>
{/each}

<ConfirmModal
  show={pending !== null}
  title={pending?.action === 'rotate' ? 'Rotate API Key' : 'Revoke API Key'}
  message={pending?.action === 'rotate'
    ? `Rotating "${pending?.key.label}" invalidates only this key. Anything using it stops working until reconfigured. Continue?`
    : `Revoking "${pending?.key.label}" is permanent. The integration using it stops working immediately. Continue?`}
  confirmText={pending?.action === 'rotate' ? 'Rotate' : 'Revoke'}
  cancelText="Cancel"
  variant="danger"
  icon={pending?.action === 'rotate' ? 'refresh' : 'trash'}
  loading={busy}
  onConfirm={confirmPending}
  onCancel={() => (pending = null)}
/>

<style>
  .key-prefix {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .key-new {
    display: flex;
    gap: var(--space-2);
    margin-top: var(--space-4);
    margin-bottom: var(--space-4);
  }

  .key-new .input {
    flex: 1;
  }

  .mcp-key-display {
    margin-bottom: var(--space-4);
  }

  .mcp-key-row {
    display: flex;
    gap: var(--space-2);
  }

  .mcp-key-row .input {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 0.8125rem;
  }

  .btn-danger-text {
    color: var(--color-danger);
  }

  .btn-danger-text:hover:not(:disabled) {
    background: var(--color-danger-light);
  }
</style>
