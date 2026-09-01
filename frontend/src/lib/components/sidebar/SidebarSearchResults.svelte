<script>
  import Icon from '../Icons.svelte';

  let { searching = false, searchError = false, hasResults = false, groups = [], ondismiss, onselect } = $props();
</script>

<div class="search-results">
  <div class="search-results-header">
    <span class="search-results-title">Search Results</span>
    <button class="search-results-close" onclick={ondismiss} aria-label="Close search results">
      <Icon name="x" size="sm" />
    </button>
  </div>
  {#if searching}
    <div class="search-loading">Searching...</div>
  {:else if searchError}
    <div class="search-empty">Search failed. Please try again.</div>
  {:else if hasResults}
    {#if groups.length === 0}
      <div class="search-empty">No results found</div>
    {:else}
      {#each groups as group}
        <div class="search-group">
          <div class="search-group-label">{group.label}</div>
          {#each group.items as item}
            <button
              class="search-result"
              onclick={() => onselect(group.type, group.getId(item))}
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

<style>
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
</style>
