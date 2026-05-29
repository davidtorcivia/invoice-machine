<script>
  import { createEventDispatcher } from 'svelte';

  export let pageStart = 0;
  export let pageEnd = 0;
  export let pagination = {
    page: 1,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_prev: false
  };
  export let loading = false;
  export let noun = 'item';

  const dispatch = createEventDispatcher();
</script>

{#if pagination.total > 0}
  <div class="pagination-bar">
    <div class="pagination-summary">
      Showing {pageStart}-{pageEnd} of {pagination.total} {noun}{pagination.total === 1 ? '' : 's'}
    </div>
    <div class="pagination-controls">
      <button class="btn btn-secondary btn-sm" on:click={() => dispatch('pagechange', pagination.page - 1)} disabled={!pagination.has_prev || loading}>
        Previous
      </button>
      <span class="pagination-page">Page {pagination.page} of {Math.max(1, pagination.total_pages)}</span>
      <button class="btn btn-secondary btn-sm" on:click={() => dispatch('pagechange', pagination.page + 1)} disabled={!pagination.has_next || loading}>
        Next
      </button>
    </div>
  </div>
{/if}

<style>
  .pagination-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    margin-top: var(--space-6);
    flex-wrap: wrap;
  }

  .pagination-summary,
  .pagination-page {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .pagination-controls {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
</style>
