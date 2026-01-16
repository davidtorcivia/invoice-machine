<script>
  import { goto } from '$app/navigation';
  import { auth, toast } from '$lib/stores';

  let username = '';
  let password = '';
  let loading = false;
  let error = '';

  async function handleSubmit() {
    error = '';
    if (!username || !password) {
      error = 'Please enter username and password';
      return;
    }

    loading = true;
    try {
      await auth.login(username, password);
      goto('/');
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Login - Invoice Machine</title>
</svelte:head>

<div class="login-page">
  <div class="login-card">
    <div class="login-header">
      <h1>Invoice Machine</h1>
      <p>Sign in to continue</p>
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
          autocomplete="username"
          disabled={loading}
        />
      </div>

      <div class="form-group">
        <label for="password" class="label">Password</label>
        <input
          id="password"
          type="password"
          class="input"
          bind:value={password}
          autocomplete="current-password"
          disabled={loading}
        />
      </div>

      <button type="submit" class="btn btn-primary btn-full" disabled={loading}>
        {loading ? 'Signing in...' : 'Sign In'}
      </button>
    </form>
  </div>
</div>

<style>
  .login-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-sunken);
    padding: var(--space-4);
  }

  .login-card {
    width: 100%;
    max-width: 400px;
    background: var(--color-bg);
    border-radius: var(--radius-xl);
    padding: var(--space-8);
    box-shadow: var(--shadow-lg);
  }

  .login-header {
    text-align: center;
    margin-bottom: var(--space-8);
  }

  .login-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--color-text);
    margin-bottom: var(--space-2);
  }

  .login-header p {
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

  .btn-full {
    width: 100%;
    margin-top: var(--space-4);
  }
</style>
