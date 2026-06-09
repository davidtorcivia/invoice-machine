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
  let searchError = false;
  let showResults = false;
  let searchInput;
  let searchContainer;
  let searchDebounce;
  let searchSeq = 0;

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

  const searchGroups = [
    {
      key: 'invoices',
      label: 'Invoices',
      icon: 'invoice',
      type: 'invoice',
      getId: (item) => item.id,
      getTitle: (item) => item.invoice_number,
      getSubtitle: (item) => item.client_name || item.client_business || 'No client'
    },
    {
      key: 'clients',
      label: 'Clients',
      icon: 'users',
      type: 'client',
      getId: (item) => item.id,
      getTitle: (item) => item.business_name || item.name,
      getSubtitle: (item) => item.email
    },
    {
      key: 'line_items',
      label: 'Line Items',
      icon: 'invoice',
      type: 'invoice',
      getId: (item) => item.invoice_id,
      getTitle: (item) => item.description,
      getSubtitle: (item) => `${item.invoice_number} - ${item.client_name || item.client_business || 'No client'}`
    }
  ];

  async function handleLogout() {
    await auth.logout();
    goto('/login');
  }

  async function handleSearch() {
    const query = searchQuery.trim();
    if (!query) {
      searchResults = null;
      showResults = false;
      return;
    }

    // Sequence token: ignore a slow earlier response that resolves after a newer
    // query, so stale results can't overwrite fresh ones.
    const seq = ++searchSeq;
    searching = true;
    searchError = false;
    showResults = true;
    try {
      const results = await searchApi.search(query, { limit: 10 });
      if (seq !== searchSeq) return;
      searchResults = results;
    } catch (error) {
      if (seq !== searchSeq) return;
      console.error('Search failed:', error);
      searchResults = null;
      searchError = true;
    } finally {
      if (seq === searchSeq) searching = false;
    }
  }

  function handleSearchInput() {
    clearTimeout(searchDebounce);
    if (searchQuery.trim().length >= 2) {
      searchDebounce = setTimeout(handleSearch, 250);
    } else {
      searchSeq++; // cancel any in-flight request's result
      searchResults = null;
      searchError = false;
      showResults = false;
      searching = false;
    }
  }

  function handleSearchKeydown(e) {
    if (e.key === 'Enter') {
      clearTimeout(searchDebounce);
      handleSearch();
    } else if (e.key === 'Escape') {
      closeSearch();
    }
  }

  function dismissSearchResults() {
    showResults = false;
  }

  function closeSearch() {
    clearTimeout(searchDebounce);
    searchSeq++;
    showResults = false;
    searchQuery = '';
    searchResults = null;
    searchError = false;
  }

  function handleWindowPointerDown(event) {
    if (!showResults || !searchContainer) return;
    if (!searchContainer.contains(/** @type {Node} */ (event.target))) {
      dismissSearchResults();
    }
  }

  function closeSidebarOnMobile() {
    if (window.innerWidth < 768) {
      sidebarOpen.set(false);
    }
  }

  function navigateToResult(type, id) {
    closeSearch();
    closeSidebarOnMobile();
    const path = type === 'invoice' ? `/invoices/${id}` : `/clients/${id}`;
    goto(path);
  }

  // Reactive current path to ensure menu updates on navigation
  $: currentPath = $page.url.pathname;
  $: visibleSearchGroups = searchGroups
    .map((group) => ({ ...group, items: searchResults?.[group.key] || [] }))
    .filter((group) => group.items.length > 0);

  function isActive(path, current) {
    if (path === '/dashboard') {
      return current === '/' || current === '/dashboard';
    }
    return current.startsWith(path);
  }
</script>

<svelte:window on:mousedown={handleWindowPointerDown} />

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
  <div class="sidebar-search" bind:this={searchContainer}>
    <div class="search-input-wrapper">
      <Icon name="search" size="sm" />
      <input
        type="text"
        class="search-input"
        placeholder="Search..."
        bind:value={searchQuery}
        bind:this={searchInput}
        on:keydown={handleSearchKeydown}
        on:focus={() => searchResults && (showResults = true)}
        on:input={handleSearchInput}
      />
      {#if searchQuery}
        <button class="search-clear" on:click={closeSearch}>
          <Icon name="x" size="sm" />
        </button>
      {/if}
    </div>

    {#if showResults}
      <div class="search-results">
        <div class="search-results-header">
          <span class="search-results-title">Search Results</span>
          <button class="search-results-close" on:click={dismissSearchResults} aria-label="Close search results">
            <Icon name="x" size="sm" />
          </button>
        </div>
        {#if searching}
          <div class="search-loading">Searching...</div>
        {:else if searchError}
          <div class="search-empty">Search failed. Please try again.</div>
        {:else if searchResults}
          {#if visibleSearchGroups.length === 0}
            <div class="search-empty">No results found</div>
          {:else}
            {#each visibleSearchGroups as group}
              <div class="search-group">
                <div class="search-group-label">{group.label}</div>
                {#each group.items as item}
                  <button
                    class="search-result"
                    on:click={() => navigateToResult(group.type, group.getId(item))}
                  >
                    <Icon name={group.icon} size="sm" />
                    <div class="search-result-info">
                      <span class="search-result-title">{group.getTitle(item)}</span>
                      {#if group.getSubtitle(item)}
                        <span class="search-result-subtitle">{group.getSubtitle(item)}</span>
                      {/if}
                    </div>
                  </button>
                {/each}
              </div>
            {/each}
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
        on:click={closeSidebarOnMobile}
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

  .search-results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4) var(--space-2);
    border-bottom: 1px solid var(--color-border-light);
  }

  .search-results-title {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--color-text-tertiary);
  }

  .search-results-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: none;
    color: var(--color-text-tertiary);
    border-radius: var(--radius-sm);
    padding: var(--space-1);
    cursor: pointer;
    transition: background-color var(--transition-fast), color var(--transition-fast);
  }

  .search-results-close:hover {
    color: var(--color-text);
    background: var(--color-bg-hover);
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
