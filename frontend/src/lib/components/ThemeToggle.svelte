<script>
  import { theme } from '$lib/stores';
  import Icon from './Icons.svelte';

  $: currentTheme = $theme;
  $: icon = currentTheme === 'light' ? 'sun' : currentTheme === 'dark' ? 'moon' : 'monitor';
  $: label = currentTheme === 'light' ? 'Light' : currentTheme === 'dark' ? 'Dark' : 'System';
</script>

<button
  class="theme-toggle"
  on:click={theme.toggle}
  title="Toggle theme ({label})"
  aria-label="Toggle theme, currently {label}"
>
  <Icon name={icon} size="sm" />
  <span class="theme-label">{label}</span>
</button>

<style>
  .theme-toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: all var(--transition-fast);
    width: 100%;
    justify-content: center;
  }

  .theme-toggle:hover {
    background: var(--color-bg-hover);
    color: var(--color-text);
    border-color: var(--color-border);
  }

  .theme-label {
    min-width: 50px;
    text-align: left;
  }
</style>
