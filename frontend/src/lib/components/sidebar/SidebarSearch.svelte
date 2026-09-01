<script>
  import { goto } from '$app/navigation';
  import { searchApi } from '$lib/api';
  import Icon from '../Icons.svelte';
  import SidebarSearchResults from './SidebarSearchResults.svelte';

  let { onnavigate = () => {} } = $props();

  let searchQuery = $state('');
  let searchResults = $state(/** @type {any} */ (null));
  let searching = $state(false);
  let searchError = $state(false);
  let showResults = $state(false);
  let searchContainer = $state();
  let searchDebounce;
  let searchSeq = 0;

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
      showResults = false;
    }
  }

  function navigateToResult(type, id) {
    closeSearch();
    onnavigate();
    goto(type === 'invoice' ? `/invoices/${id}` : `/clients/${id}`);
  }

  let visibleSearchGroups = $derived(searchGroups
    .map((group) => ({ ...group, items: searchResults?.[group.key] || [] }))
    .filter((group) => group.items.length > 0));
</script>

<svelte:window onmousedown={handleWindowPointerDown} />

<div class="sidebar-search" bind:this={searchContainer}>
  <div class="search-input-wrapper">
    <Icon name="search" size="sm" />
    <input
      type="text"
      class="search-input"
      placeholder="Search..."
      aria-label="Search"
      bind:value={searchQuery}
      onkeydown={handleSearchKeydown}
      onfocus={() => searchResults && (showResults = true)}
      oninput={handleSearchInput}
    />
    {#if searchQuery}
      <button class="search-clear" aria-label="Clear search" onclick={closeSearch}>
        <Icon name="x" size="sm" />
      </button>
    {/if}
  </div>

  {#if showResults}
    <SidebarSearchResults
      {searching}
      {searchError}
      hasResults={!!searchResults}
      groups={visibleSearchGroups}
      ondismiss={() => (showResults = false)}
      onselect={navigateToResult}
    />
  {/if}
</div>

<style>
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
</style>
