<script>
  import { createEventDispatcher } from 'svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let clients = [];
  export let sortOptions = [];
  export let yearOptions = [];
  export let selectedSortOption = '';
  export let filterStatus = '';
  export let filterClient = '';
  export let filterDocumentType = '';
  export let filterYear = '';
  export let filterFromDate = '';
  export let filterToDate = '';
  export let hasFilters = false;

  const dispatch = createEventDispatcher();

  function handleSortChange(event) {
    dispatch('sortchange', /** @type {HTMLSelectElement} */ (event.currentTarget).value);
  }
</script>

<div class="filters-bar">
  <div class="filters-row">
    <div class="filter-group">
      <label for="status-filter" class="filter-label">Status</label>
      <select id="status-filter" class="select" bind:value={filterStatus} on:change={() => dispatch('filterchange')}>
        <option value="">All Statuses</option>
        <option value="draft">Draft</option>
        <option value="sent">Sent</option>
        <option value="paid">Paid</option>
        <option value="overdue">Overdue</option>
        <option value="cancelled">Cancelled</option>
      </select>
    </div>

    <div class="filter-group">
      <label for="type-filter" class="filter-label">Type</label>
      <select id="type-filter" class="select" bind:value={filterDocumentType} on:change={() => dispatch('filterchange')}>
        <option value="">All Types</option>
        <option value="invoice">Invoices</option>
        <option value="quote">Quotes</option>
      </select>
    </div>

    <div class="filter-group">
      <label for="client-filter" class="filter-label">Client</label>
      <select id="client-filter" class="select" bind:value={filterClient} on:change={() => dispatch('filterchange')}>
        <option value="">All Clients</option>
        {#each clients as client}
          <option value={client.id}>{client.business_name || client.name}</option>
        {/each}
      </select>
    </div>

    <div class="filter-group">
      <label for="year-filter" class="filter-label">Year</label>
      <select id="year-filter" class="select" bind:value={filterYear} on:change={() => dispatch('yearchange')}>
        <option value="">All Years</option>
        {#each yearOptions as year}
          <option value={year}>{year}</option>
        {/each}
      </select>
    </div>

    <fieldset class="filter-group date-range-group">
      <legend class="filter-label">Date Range</legend>
      <div class="date-range-inputs">
        <input
          id="from-date-filter"
          type="date"
          class="input input-sm"
          bind:value={filterFromDate}
          on:change={() => dispatch('datechange')}
          placeholder="From"
        />
        <span class="date-range-separator">to</span>
        <input
          id="to-date-filter"
          type="date"
          class="input input-sm"
          bind:value={filterToDate}
          on:change={() => dispatch('datechange')}
          placeholder="To"
        />
      </div>
    </fieldset>

    <div class="filter-group sort-dropdown-mobile">
      <label for="sort-select" class="filter-label">Sort</label>
      <select id="sort-select" class="select" value={selectedSortOption} on:change={handleSortChange}>
        {#each sortOptions as option}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
    </div>
  </div>

  {#if hasFilters}
    <button class="btn btn-ghost btn-sm clear-filters" on:click={() => dispatch('clear')}>
      <Icon name="x" size="sm" />
      Clear filters
    </button>
  {/if}
</div>

<style>
  .filters-bar {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin-bottom: var(--space-6);
    padding: var(--space-5);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .filters-row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-4);
  }

  .filter-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 140px;
  }

  .filter-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .date-range-group {
    border: 0;
    padding: 0;
    margin: 0;
    min-width: auto;
  }

  .date-range-group legend {
    padding: 0;
  }

  .date-range-inputs {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .date-range-inputs .input {
    width: 155px;
  }

  .date-range-separator {
    color: var(--color-text-tertiary);
    font-size: 0.8125rem;
  }

  .sort-dropdown-mobile {
    display: none;
  }

  .clear-filters {
    align-self: flex-start;
    color: var(--color-text-secondary);
  }

  @media (max-width: 768px) {
    .sort-dropdown-mobile {
      display: flex;
    }
  }
</style>
