<script>
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores';

  let username = '';
  let password = '';
  let confirmPassword = '';
  let loading = false;
  let error = '';

  async function handleSubmit() {
    error = '';

    if (!username || !password) {
      error = 'Please fill in all fields';
      return;
    }

    if (username.length < 3) {
      error = 'Username must be at least 3 characters';
      return;
    }

    if (password.length < 8) {
      error = 'Password must be at least 8 characters';
      return;
    }

    if (password !== confirmPassword) {
      error = 'Passwords do not match';
      return;
    }

    loading = true;
    try {
      await auth.setup(username, password);
      goto('/');
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Setup - Invoice Machine</title>
</svelte:head>

<div class="setup-page">
  <div class="setup-card">
    <div class="setup-header">
      <h1>Welcome to Invoice Machine</h1>
      <p>Create your account to get started</p>
    </div>

    <form on:submit|preventDefault={handleSubmit}>
      {#if error}
        <div class="error-message">{error}</div>
      {/if}

      <div class="form-group">
        <label for="username" class="label">Username</label>
        <input
          id="username"
          type="text"
          class="input"
          bind:value={username}
          placeholder="Choose a username"
          autocomplete="username"
          disabled={loading}
        />
        <p class="form-hint">At least 3 characters</p>
      </div>

      <div class="form-group">
        <label for="password" class="label">Password</label>
        <input
          id="password"
          type="password"
          class="input"
          bind:value={password}
          placeholder="Choose a secure password"
          autocomplete="new-password"
          disabled={loading}
        />
        <p class="form-hint">At least 8 characters</p>
      </div>

      <div class="form-group">
        <label for="confirm-password" class="label">Confirm Password</label>
        <input
          id="confirm-password"
          type="password"
          class="input"
          bind:value={confirmPassword}
          placeholder="Confirm your password"
          autocomplete="new-password"
          disabled={loading}
        />
      </div>

      <button type="submit" class="btn btn-primary btn-full" disabled={loading}>
        {loading ? 'Creating Account...' : 'Create Account'}
      </button>
    </form>
  </div>
</div>

<style>
  .setup-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-sunken);
    padding: var(--space-4);
  }

  .setup-card {
    width: 100%;
    max-width: 440px;
    background: var(--color-bg);
    border-radius: var(--radius-xl);
    padding: var(--space-8);
    box-shadow: var(--shadow-lg);
  }

  .setup-header {
    text-align: center;
    margin-bottom: var(--space-8);
  }

  .setup-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--color-text);
    margin-bottom: var(--space-2);
  }

  .setup-header p {
    color: var(--color-text-secondary);
  }

  .error-message {
    background: var(--color-danger-light);
    color: var(--color-danger);
    padding: var(--space-3);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-4);
    font-size: 0.875rem;
  }

  .form-group {
    margin-bottom: var(--space-4);
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  .btn-full {
    width: 100%;
    margin-top: var(--space-4);
  }
</style>
