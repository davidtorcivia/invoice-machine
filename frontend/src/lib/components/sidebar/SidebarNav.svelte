<script>
  import { page } from '$app/stores';
  import Icon from '../Icons.svelte';

  let { onnavigate = () => {} } = $props();

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: 'home' },
    { path: '/invoices', label: 'Invoices', icon: 'invoice' },
    { path: '/recurring', label: 'Recurring', icon: 'repeat' },
    { path: '/clients', label: 'Clients', icon: 'users' },
    { path: '/reports', label: 'Reports', icon: 'chart' },
    { path: '/settings', label: 'Settings', icon: 'settings' },
    { path: '/trash', label: 'Trash', icon: 'trash' },
    { path: '/help', label: 'Help', icon: 'help' },
  ];

  let currentPath = $derived($page.url.pathname);

  function isActive(path, current) {
    if (path === '/dashboard') {
      return current === '/' || current === '/dashboard';
    }
    return current.startsWith(path);
  }
</script>

<nav class="sidebar-nav">
  {#each navItems as item}
    <a
      href={item.path}
      class="nav-item"
      class:active={isActive(item.path, currentPath)}
      onclick={() => onnavigate()}
    >
      <Icon name={item.icon} size="md" />
      <span>{item.label}</span>
    </a>
  {/each}
</nav>

<style>
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

  @media (max-width: 768px) {
    /* Move footer right below nav on mobile */
    .sidebar-nav {
      flex: none;
    }
  }
</style>
