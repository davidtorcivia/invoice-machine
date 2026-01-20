<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { sidebarOpen, toggleSidebar, auth } from '$lib/stores';
  import { searchApi } from '$lib/api';
  import Icon from './Icons.svelte';
  import ThemeToggle from './ThemeToggle.svelte';

  let searchQuery = '';
  let searchResults = null;
  let searching = false;
  let showResults = false;
  let searchInput;

  async function handleLogout() {
    await auth.logout();
    goto('/login');
  }

  async function handleSearch() {
    if (!searchQuery.trim()) {
      searchResults = null;
      showResults = false;
      return;
    }

    searching = true;
    showResults = true;
    try {
      searchResults = await searchApi.search(searchQuery.trim(), { limit: 10 });
    } catch (error) {
      console.error('Search failed:', error);
      searchResults = { invoices: [], clients: [] };
    } finally {
      searching = false;
    }
  }

  function handleSearchKeydown(e) {
    if (e.key === 'Enter') {
      handleSearch();
    } else if (e.key === 'Escape') {
      closeSearch();
    }
  }

  function closeSearch() {
    showResults = false;
    searchQuery = '';
    searchResults = null;
  }

  function navigateToResult(type, id) {
    closeSearch();
    if (window.innerWidth < 768) {
      sidebarOpen.set(false);
    }
    if (type === 'invoice') {
      goto(`/invoices/${id}`);
    } else {
      goto(`/clients/${id}`);
    }
  }

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

  <!-- Search Bar -->
  <div class="sidebar-search">
    <div class="search-input-wrapper">
      <Icon name="search" size="sm" />
      <input
        type="text"
        class="search-input"
        placeholder="Search..."
        bind:value={searchQuery}
        bind:this={searchInput}
        on:keydown={handleSearchKeydown}
        on:input={() => searchQuery.length >= 2 && handleSearch()}
      />
      {#if searchQuery}
        <button class="search-clear" on:click={closeSearch}>
          <Icon name="x" size="sm" />
        </button>
      {/if}
    </div>

    {#if showResults}
      <div class="search-results">
        {#if searching}
          <div class="search-loading">Searching...</div>
        {:else if searchResults}
          {#if searchResults.invoices?.length === 0 && searchResults.clients?.length === 0 && searchResults.line_items?.length === 0}
            <div class="search-empty">No results found</div>
          {:else}
            {#if searchResults.invoices?.length > 0}
              <div class="search-group">
                <div class="search-group-label">Invoices</div>
                {#each searchResults.invoices as invoice}
                  <button
                    class="search-result"
                    on:click={() => navigateToResult('invoice', invoice.id)}
                  >
                    <Icon name="invoice" size="sm" />
                    <div class="search-result-info">
                      <span class="search-result-title">{invoice.invoice_number}</span>
                      <span class="search-result-subtitle">{invoice.client_name || invoice.client_business || 'No client'}</span>
                    </div>
                  </button>
                {/each}
              </div>
            {/if}
            {#if searchResults.clients?.length > 0}
              <div class="search-group">
                <div class="search-group-label">Clients</div>
                {#each searchResults.clients as client}
                  <button
                    class="search-result"
                    on:click={() => navigateToResult('client', client.id)}
                  >
                    <Icon name="users" size="sm" />
                    <div class="search-result-info">
                      <span class="search-result-title">{client.business_name || client.name}</span>
                      {#if client.email}
                        <span class="search-result-subtitle">{client.email}</span>
                      {/if}
                    </div>
                  </button>
                {/each}
              </div>
            {/if}
            {#if searchResults.line_items?.length > 0}
              <div class="search-group">
                <div class="search-group-label">Line Items</div>
                {#each searchResults.line_items as item}
                  <button
                    class="search-result"
                    on:click={() => navigateToResult('invoice', item.invoice_id)}
                  >
                    <Icon name="invoice" size="sm" />
                    <div class="search-result-info">
                      <span class="search-result-title">{item.description}</span>
                      <span class="search-result-subtitle">{item.invoice_number} - {item.client_name || item.client_business || 'No client'}</span>
                    </div>
                  </button>
                {/each}
              </div>
            {/if}
          {/if}
        {/if}
      </div>
    {/if}
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
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  /* Search */
  .sidebar-search {
    padding: 0 var(--space-4) var(--space-3);
    position: relative;
  }

  .search-input-wrapper {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-3);
    transition: border-color var(--transition-fast);
  }

  .search-input-wrapper:focus-within {
    border-color: var(--color-primary);
  }

  .search-input-wrapper :global(.icon) {
    color: var(--color-text-tertiary);
    flex-shrink: 0;
  }

  .search-input {
    flex: 1;
    border: none;
    background: none;
    font-size: 0.875rem;
    color: var(--color-text);
    outline: none;
    min-width: 0;
  }

  .search-input::placeholder {
    color: var(--color-text-tertiary);
  }

  .search-clear {
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    padding: var(--space-1);
    cursor: pointer;
    color: var(--color-text-tertiary);
    border-radius: var(--radius-sm);
  }

  .search-clear:hover {
    color: var(--color-text);
    background: var(--color-bg-hover);
  }

  .search-results {
    position: absolute;
    top: 100%;
    left: var(--space-4);
    right: var(--space-4);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg);
    z-index: 100;
    max-height: 320px;
    overflow-y: auto;
    margin-top: var(--space-1);
  }

  .search-loading,
  .search-empty {
    padding: var(--space-4);
    text-align: center;
    color: var(--color-text-tertiary);
    font-size: 0.875rem;
  }

  .search-group {
    padding: var(--space-2);
  }

  .search-group-label {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-tertiary);
    padding: var(--space-2) var(--space-2);
  }

  .search-result {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-2) var(--space-2);
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    text-align: left;
    transition: background-color var(--transition-fast);
  }

  .search-result:hover {
    background: var(--color-bg-hover);
  }

  .search-result :global(.icon) {
    color: var(--color-text-tertiary);
    flex-shrink: 0;
  }

  .search-result-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .search-result-title {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .search-result-subtitle {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
      padding-top: var(--space-6);
    }
  }
</style>
