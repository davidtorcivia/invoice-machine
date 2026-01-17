<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { sidebarOpen, toggleSidebar, auth } from '$lib/stores';
  import Icon from './Icons.svelte';
  import ThemeToggle from './ThemeToggle.svelte';

  async function handleLogout() {
    await auth.logout();
    goto('/login');
  }

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: 'home' },
    { path: '/invoices', label: 'Invoices', icon: 'invoice' },
    { path: '/clients', label: 'Clients', icon: 'users' },
    { path: '/settings', label: 'Settings', icon: 'settings' },
    { path: '/trash', label: 'Trash', icon: 'trash' },
    { path: '/help', label: 'Help', icon: 'help' },
  ];

  // Reactive current path to ensure menu updates on navigation
  $: currentPath = $page.url.pathname;

  function isActive(path, current) {
    if (path === '/dashboard') {
      return current === '/' || current === '/dashboard';
    }
    return current.startsWith(path);
  }
</script>

<!-- Mobile overlay -->
{#if $sidebarOpen}
  <div
    class="sidebar-overlay"
    on:click={toggleSidebar}
    on:keydown={(e) => e.key === 'Escape' && toggleSidebar()}
    role="button"
    tabindex="-1"
    aria-label="Close sidebar"
  ></div>
{/if}

<aside class="sidebar" class:open={$sidebarOpen}>
  <div class="sidebar-header">
    <div class="logo">
      <span class="logo-mark">Invoice</span>
      <span class="logo-text">Machine</span>
    </div>
    <button class="btn btn-ghost btn-icon mobile-close" on:click={toggleSidebar}>
      <Icon name="x" size="md" />
    </button>
  </div>

  <nav class="sidebar-nav">
    {#each navItems as item}
      <a
        href={item.path}
        class="nav-item"
        class:active={isActive(item.path, currentPath)}
        on:click={() => {
          if (window.innerWidth < 768) {
            sidebarOpen.set(false);
          }
        }}
      >
        <Icon name={item.icon} size="md" />
        <span>{item.label}</span>
      </a>
    {/each}
  </nav>

  <div class="sidebar-footer">
    <ThemeToggle />
    <button class="logout-btn" on:click={handleLogout}>
      <Icon name="logout" size="sm" />
      <span>Sign Out</span>
    </button>
  </div>
</aside>

<style>
  .sidebar-overlay {
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 0.3);
    z-index: 45;
    display: none;
  }

  .sidebar {
    width: var(--sidebar-width);
    background: var(--color-bg-elevated);
    border-right: 1px solid var(--color-border);
    height: 100vh;
    position: fixed;
    left: 0;
    top: 0;
    display: flex;
    flex-direction: column;
    z-index: 50;
    transition: transform var(--transition-slow);
  }

  .sidebar-header {
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--color-border-light);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .logo {
    font-size: 1.375rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    display: flex;
  }

  .logo-mark {
    color: var(--color-primary);
  }

  .logo-text {
    color: var(--color-text);
  }

  .mobile-close {
    display: none;
  }

  .sidebar-nav {
    flex: 1;
    padding: var(--space-4) var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    overflow-y: auto;
    min-height: 0;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    text-decoration: none;
    border-radius: var(--radius-md);
    transition: all var(--transition-fast);
  }

  .nav-item:hover {
    color: var(--color-text);
    background: var(--color-bg-hover);
  }

  .nav-item.active {
    color: var(--color-primary);
    background: var(--color-primary-light);
  }

  .sidebar-footer {
    padding: var(--space-4) var(--space-6);
    border-top: 1px solid var(--color-border-light);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .logout-btn {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-3) var(--space-3);
    background: none;
    border: 1px solid color-mix(in srgb, var(--color-danger) 30%, var(--color-border));
    border-radius: var(--radius-md);
    color: color-mix(in srgb, var(--color-danger) 70%, var(--color-text-secondary));
    font-size: 0.875rem;
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .logout-btn:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
    background: var(--color-danger-light);
  }

  @media (max-width: 768px) {
    .sidebar-overlay {
      display: block;
    }

    .sidebar {
      transform: translateX(-100%);
    }

    .sidebar.open {
      transform: translateX(0);
    }

    .mobile-close {
      display: flex;
    }

    /* Move footer right below nav on mobile */
    .sidebar-nav {
      flex: none;
    }

    .sidebar-footer {
      flex-shrink: 0;
      border-top: none;
      padding-top: var(--space-6);
    }
  }
</style>
