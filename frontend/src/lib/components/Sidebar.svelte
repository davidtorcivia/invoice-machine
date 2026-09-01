<script>
  import { sidebarOpen, toggleSidebar } from '$lib/stores';
  import Icon from './Icons.svelte';
  import SidebarSearch from './sidebar/SidebarSearch.svelte';
  import SidebarNav from './sidebar/SidebarNav.svelte';
  import SidebarFooter from './sidebar/SidebarFooter.svelte';

  function closeSidebarOnMobile() {
    if (window.innerWidth < 768) {
      sidebarOpen.set(false);
    }
  }
</script>

{#if $sidebarOpen}
  <div
    class="sidebar-overlay"
    onclick={toggleSidebar}
    onkeydown={(e) => e.key === 'Escape' && toggleSidebar()}
    role="button"
    tabindex="-1"
    aria-label="Close sidebar"
  ></div>
{/if}

<aside class="sidebar" class:open={$sidebarOpen}>
  <div class="sidebar-header">
    <div class="logo">
      <span class="logo-mark">Invoice</span>
      <span class="logo-text">Machine</span>
    </div>
    <button class="btn btn-ghost btn-icon mobile-close" onclick={toggleSidebar}>
      <Icon name="x" size="md" />
    </button>
  </div>

  <SidebarSearch onnavigate={closeSidebarOnMobile} />
  <SidebarNav onnavigate={closeSidebarOnMobile} />
  <SidebarFooter />
</aside>

<style>
  .sidebar-overlay {
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 0.3);
    z-index: 45;
    display: none;
  }

  .sidebar {
    width: var(--sidebar-width);
    background: var(--color-bg-elevated);
    border-right: 1px solid var(--color-border);
    height: 100vh;
    position: fixed;
    left: 0;
    top: 0;
    display: flex;
    flex-direction: column;
    z-index: 50;
    transition: transform var(--transition-slow);
  }

  .sidebar-header {
    padding: var(--space-5) var(--space-6);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .logo {
    font-size: 1.375rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    display: flex;
  }

  .logo-mark {
    color: var(--color-primary);
  }

  .logo-text {
    color: var(--color-text);
  }

  .mobile-close {
    display: none;
  }

  @media (max-width: 768px) {
    .sidebar-overlay {
      display: block;
    }

    .sidebar {
      transform: translateX(-100%);
    }

    .sidebar.open {
      transform: translateX(0);
    }

    .mobile-close {
      display: flex;
    }
  }
</style>
