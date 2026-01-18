<script>
  import Icon from './Icons.svelte';

  export let title = '';
  export let subtitle = '';
  export let open = false;
  export let icon = null;

  function toggle() {
    open = !open;
  }
</script>

<div class="collapsible" class:open>
  <button class="collapsible-header" on:click={toggle} type="button">
    <div class="collapsible-title">
      {#if icon}
        <Icon name={icon} size="sm" />
      {/if}
      <div class="collapsible-text">
        <h3>{title}</h3>
        {#if subtitle}
          <p class="collapsible-subtitle">{subtitle}</p>
        {/if}
      </div>
    </div>
    <Icon name={open ? 'chevronUp' : 'chevronDown'} size="sm" />
  </button>

  {#if open}
    <div class="collapsible-content">
      <slot />
    </div>
  {/if}
</div>

<style>
  .collapsible {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .collapsible-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    transition: background-color 0.15s ease;
    color: var(--color-text-secondary);
  }

  .collapsible-header:hover {
    background: var(--color-bg-hover);
  }

  .collapsible-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .collapsible-title h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .collapsible-subtitle {
    margin: 0.25rem 0 0 0;
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
  }

  .collapsible-text {
    display: flex;
    flex-direction: column;
  }

  .collapsible-content {
    padding: 0 1.25rem 1.25rem;
    animation: slideDown 0.2s ease;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>
