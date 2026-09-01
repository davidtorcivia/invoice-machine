<script>
  import Icon from '$lib/components/Icons.svelte';

  let { labels = [], saving = false, ondiscard, onsave } = $props();
</script>

<div class="save-bar" role="status">
  <span class="save-bar-text">
    Unsaved changes
    <span class="save-bar-sections">{labels.join(' · ')}</span>
  </span>
  <div class="save-bar-actions">
    <button type="button" class="btn btn-secondary" onclick={ondiscard} disabled={saving}>
      Discard
    </button>
    <button type="button" class="btn btn-primary" onclick={onsave} disabled={saving}>
      {#if saving}
        <span class="spinner-sm"></span>
        Saving...
      {:else}
        <Icon name="check" size="sm" />
        Save Changes
      {/if}
    </button>
  </div>
</div>

<style>
  .save-bar {
    position: sticky;
    bottom: var(--space-4);
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    margin-top: var(--space-6);
    padding: var(--space-3) var(--space-4);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    animation: save-bar-in 0.15s ease;
  }

  @keyframes save-bar-in {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .save-bar-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text);
    min-width: 0;
  }

  .save-bar-sections {
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--color-text-tertiary);
  }

  .save-bar-actions {
    display: flex;
    gap: var(--space-2);
    flex-shrink: 0;
  }

  @media (max-width: 768px) {
    .save-bar {
      bottom: var(--space-3);
    }
  }

  @media (max-width: 480px) {
    .save-bar {
      flex-direction: column;
      align-items: stretch;
      text-align: center;
    }

    .save-bar-actions .btn {
      flex: 1;
    }
  }
</style>
