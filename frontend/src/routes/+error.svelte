<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import Icon from '$lib/components/Icons.svelte';

  $: status = $page.status;
  $: message = $page.error?.message;

  // Error configurations based on status code
  const errorConfigs = {
    401: {
      title: 'Unauthorized',
      description: 'You need to sign in to access this page.',
      icon: 'user',
      action: 'Sign In',
      actionPath: '/login'
    },
    403: {
      title: 'Forbidden',
      description: 'You don\'t have permission to access this resource.',
      icon: 'warning',
      action: 'Go Home',
      actionPath: '/'
    },
    404: {
      title: 'Page Not Found',
      description: 'The page you\'re looking for doesn\'t exist or has been moved.',
      icon: 'search',
      action: 'Go Home',
      actionPath: '/'
    },
    500: {
      title: 'Server Error',
      description: 'Something went wrong on our end. Please try again later.',
      icon: 'server',
      action: 'Try Again',
      actionPath: null // Will reload
    }
  };

  $: config = errorConfigs[status] || {
    title: 'Error',
    description: message || 'An unexpected error occurred.',
    icon: 'warning',
    action: 'Go Home',
    actionPath: '/'
  };

  function handleAction() {
    if (config.actionPath) {
      goto(config.actionPath);
    } else {
      window.location.reload();
    }
  }
</script>

<svelte:head>
  <title>{status} - {config.title} | Invoice Machine</title>
</svelte:head>

<div class="error-page">
  <div class="error-container">
    <!-- Error Status Badge -->
    <div class="error-badge">
      <span class="error-code">{status}</span>
    </div>

    <!-- Error Icon -->
    <div class="error-icon">
      <Icon name={config.icon} size="xl" />
    </div>

    <!-- Error Content -->
    <h1 class="error-title">{config.title}</h1>
    <p class="error-description">{config.description}</p>

    {#if message && message !== config.description}
      <div class="error-details">
        <code>{message}</code>
      </div>
    {/if}

    <!-- Actions -->
    <div class="error-actions">
      <button class="btn btn-primary" on:click={handleAction}>
        <Icon name={config.actionPath === '/login' ? 'user' : config.actionPath ? 'home' : 'refresh'} size="sm" />
        {config.action}
      </button>

      {#if config.actionPath !== '/'}
        <button class="btn btn-secondary" on:click={() => goto('/')}>
          <Icon name="home" size="sm" />
          Go Home
        </button>
      {/if}
    </div>

    <!-- Helpful Links -->
    <div class="error-links">
      <a href="/dashboard">Dashboard</a>
      <span class="divider">•</span>
      <a href="/invoices">Invoices</a>
      <span class="divider">•</span>
      <a href="/clients">Clients</a>
      <span class="divider">•</span>
      <a href="/help">Help</a>
    </div>
  </div>

  <!-- Decorative background pattern -->
  <div class="error-pattern" aria-hidden="true">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none">
      <defs>
        <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M 10 0 L 0 0 0 10" fill="none" stroke="currentColor" stroke-width="0.5" opacity="0.1"/>
        </pattern>
      </defs>
      <rect width="100" height="100" fill="url(#grid)"/>
    </svg>
  </div>
</div>

<style>
  .error-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg);
    padding: var(--space-6);
    position: relative;
    overflow: hidden;
  }

  .error-container {
    text-align: center;
    max-width: 480px;
    width: 100%;
    z-index: 1;
  }

  .error-badge {
    display: inline-block;
    margin-bottom: var(--space-6);
  }

  .error-code {
    display: inline-block;
    font-size: 4rem;
    font-weight: 800;
    font-family: var(--font-mono);
    background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark, #0d7a2e));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
    letter-spacing: -0.02em;
  }

  .error-icon {
    width: 80px;
    height: 80px;
    margin: 0 auto var(--space-6);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-secondary);
    box-shadow: var(--shadow-md);
  }

  .error-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--color-text);
    margin-bottom: var(--space-3);
    letter-spacing: -0.02em;
  }

  .error-description {
    font-size: 1rem;
    color: var(--color-text-secondary);
    margin-bottom: var(--space-6);
    line-height: 1.6;
  }

  .error-details {
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    margin-bottom: var(--space-6);
  }

  .error-details code {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    word-break: break-word;
  }

  .error-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: center;
    margin-bottom: var(--space-8);
    flex-wrap: wrap;
  }

  .error-actions .btn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  .error-links {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .error-links a {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    text-decoration: none;
    transition: color var(--transition-fast);
  }

  .error-links a:hover {
    color: var(--color-primary);
  }

  .error-links .divider {
    color: var(--color-border);
    font-size: 0.75rem;
  }

  .error-pattern {
    position: absolute;
    inset: 0;
    pointer-events: none;
    color: var(--color-text);
  }

  .error-pattern svg {
    width: 100%;
    height: 100%;
  }

  /* Responsive adjustments */
  @media (max-width: 480px) {
    .error-page {
      padding: var(--space-4);
    }

    .error-code {
      font-size: 3rem;
    }

    .error-icon {
      width: 64px;
      height: 64px;
    }

    .error-title {
      font-size: 1.5rem;
    }

    .error-description {
      font-size: 0.9375rem;
    }

    .error-actions {
      flex-direction: column;
    }

    .error-actions .btn {
      width: 100%;
      justify-content: center;
    }

    .error-links {
      flex-direction: column;
      gap: var(--space-2);
    }

    .error-links .divider {
      display: none;
    }
  }
</style>
