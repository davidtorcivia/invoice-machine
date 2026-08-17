<script lang="ts">
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  interface Props {
    open?: boolean;
    username?: string | null;
    changing?: boolean;
    onchange: (currentPassword: string, newPassword: string) => Promise<void> | void;
  }

  let {
    open = $bindable(false),
    username = null,
    changing = false,
    onchange
  }: Props = $props();

  let currentPassword = $state('');
  let newPassword = $state('');
  let confirmPassword = $state('');
  let localError = $state('');

  async function submit() {
    localError = '';
    if (newPassword !== confirmPassword) {
      localError = 'New password and confirmation do not match';
      return;
    }
    try {
      await onchange(currentPassword, newPassword);
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
    } catch {
      // Parent already toasted the failure; keep the fields so the user can retry.
    }
  }
</script>

<CollapsibleSection title="Account" subtitle="Change your sign-in password" icon="user" bind:open={open}>
  {#if username}
    <p class="form-hint mb-4">Signed in as <strong>{username}</strong>. Changing the password signs out every other session.</p>
  {:else}
    <p class="form-hint mb-4">Changing the password signs out every other session.</p>
  {/if}

  <form class="account-form" onsubmit={(event) => { event.preventDefault(); submit(); }}>
    <div class="form-group">
      <label for="current-password" class="label">Current password</label>
      <input
        id="current-password"
        type="password"
        class="input"
        autocomplete="current-password"
        bind:value={currentPassword}
        disabled={changing}
      />
    </div>
    <div class="form-row">
      <div class="form-group">
        <label for="new-password" class="label">New password</label>
        <input
          id="new-password"
          type="password"
          class="input"
          autocomplete="new-password"
          bind:value={newPassword}
          disabled={changing}
        />
      </div>
      <div class="form-group">
        <label for="confirm-password" class="label">Confirm new password</label>
        <input
          id="confirm-password"
          type="password"
          class="input"
          autocomplete="new-password"
          bind:value={confirmPassword}
          disabled={changing}
        />
      </div>
    </div>
    {#if localError}
      <p class="form-error">{localError}</p>
    {/if}
    <button type="submit" class="btn btn-secondary" disabled={changing || !currentPassword || !newPassword || !confirmPassword}>
      {changing ? 'Updating…' : 'Update password'}
    </button>
  </form>
</CollapsibleSection>

<style>
  .account-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-error {
    color: var(--color-danger, #b91c1c);
    font-size: 0.875rem;
    margin: 0;
  }
</style>
