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
  <div class="search-input-wrapper">
    <Icon name="search" size="md" />
    <input type="text" class="search-input" placeholder="Search clients..." bind:value={searchQuery} on:keydown={handleKeydown} />
    {#if searchQuery}
      <button class="btn btn-ghost btn-icon btn-sm" on:click={() => dispatch('clear')}>
        <Icon name="x" size="sm" />
      </button>
    {/if}
  </div>
  <div class="sort-group">
    <label for="sort-select" class="sort-label">Sort</label>
    <select id="sort-select" class="select" value={selectedSortOption} on:change={handleSortChange}>
      {#each sortOptions as option}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </div>
  <button class="btn btn-secondary" on:click={() => dispatch('search')}>Search</button>
</div>

<style>
  .search-bar {
    display: flex;
    align-items: flex-end;
    gap: var(--space-3);
    margin-bottom: var(--space-6);
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
</style>
