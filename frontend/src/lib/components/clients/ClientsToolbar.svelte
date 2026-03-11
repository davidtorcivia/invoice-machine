<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let searchQuery = '';
  export let selectedSortOption = '';
  export let sortOptions = [];

  const dispatch = createEventDispatcher();

  /**
   * @param {KeyboardEvent} event
   */
  function handleKeydown(event) {
    if (event.key === 'Enter') {
      dispatch('search');
    }
  }

  /**
   * @param {Event} event
   */
  function handleSortChange(event) {
    dispatch('sortchange', /** @type {HTMLSelectElement} */ (event.currentTarget).value);
  }
</script>

<div class="search-bar">
  <div class="search-group">
    <label for="client-search" class="sort-label">Search</label>
    <div class="search-controls">
      <div class="search-input-wrapper">
        <Icon name="search" size="md" />
        <input
          id="client-search"
          type="text"
          class="search-input"
          placeholder="Search clients..."
          bind:value={searchQuery}
          on:keydown={handleKeydown}
        />
        {#if searchQuery}
          <button class="btn btn-ghost btn-icon btn-sm clear-button" on:click={() => dispatch('clear')} aria-label="Clear search">
            <Icon name="x" size="sm" />
          </button>
        {/if}
      </div>
      <button class="btn btn-secondary search-button" on:click={() => dispatch('search')}>Search</button>
    </div>
  </div>
  <div class="sort-group">
    <label for="sort-select" class="sort-label">Sort</label>
    <select id="sort-select" class="select" value={selectedSortOption} on:change={handleSortChange}>
      {#each sortOptions as option}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </div>
</div>

<style>
  .search-bar {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
    margin-bottom: var(--space-6);
    padding: var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .search-group {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .search-controls {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
  }

  .search-input-wrapper {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: 1;
    min-height: 42px;
    padding: 0 var(--space-3);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  }

  .search-input-wrapper:focus-within {
    border-color: var(--color-border-focus);
    box-shadow: 0 0 0 3px rgb(22 163 74 / 0.15);
  }

  .search-input-wrapper :global(.icon) {
    flex-shrink: 0;
    color: var(--color-text-tertiary);
  }

  .search-input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    padding: var(--space-2) 0;
  }

  .search-input:focus {
    outline: none;
  }

  .search-input::placeholder {
    color: var(--color-text-tertiary);
  }

  .clear-button {
    flex-shrink: 0;
  }

  .search-button {
    flex-shrink: 0;
  }

  .sort-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .sort-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-tertiary);
  }

  .sort-group .select {
    min-width: 180px;
  }

  @media (max-width: 768px) {
    .search-bar {
      flex-direction: column;
      align-items: stretch;
    }

    .search-controls {
      flex-direction: column;
      align-items: stretch;
    }

    .search-button,
    .sort-group .select {
      width: 100%;
    }
  }
</style>
