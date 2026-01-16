<script>
  import { toggleSidebar } from '$lib/stores';
  import Icon from './Icons.svelte';

  // Title/subtitle kept for accessibility but visually hidden
  export let title = '';
  export let subtitle = '';
</script>

<!-- Minimal header - just mobile menu toggle, no visible titles -->
<header class="header">
  <button
    class="btn btn-ghost btn-icon mobile-menu"
    on:click={toggleSidebar}
    aria-label="Toggle menu"
  >
    <Icon name="menu" size="md" />
  </button>

  <!-- Screen reader only title -->
  <h1 class="sr-only">{title}</h1>
</header>

<style>
  .header {
    display: none;
    padding: var(--space-3);
  }

  .mobile-menu {
    display: flex;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  @media (max-width: 768px) {
    .header {
      display: flex;
      position: sticky;
      top: 0;
      z-index: 30;
      background: var(--color-bg);
    }
  }
</style>
