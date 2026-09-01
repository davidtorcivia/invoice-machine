<script lang="ts">
  import '@fontsource-variable/inter';
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import Toast from '$lib/components/Toast.svelte';
  interface Props {
    children?: import('svelte').Snippet;
  }

  let { children }: Props = $props();

  const publicRoutes = ['/login', '/setup'];

  const pageTitles = {
    '/': 'Dashboard',
    '/dashboard': 'Dashboard',
    '/invoices': 'Invoices',
    '/invoices/new': 'New Invoice',
    '/clients': 'Clients',
    '/clients/new': 'New Client',
    '/settings': 'Settings',
    '/settings/email-templates': 'Email Templates',
    '/reports': 'Reports',
    '/recurring': 'Recurring',
    '/trash': 'Trash',
    '/help': 'Help',
  };

  function getPageTitle(pathname) {
    if (pageTitles[pathname]) return pageTitles[pathname];
    if (pathname.match(/^\/invoices\/\d+\/edit$/)) return 'Edit Invoice';
    if (pathname.match(/^\/invoices\/\d+$/)) return 'Invoice Details';
    if (pathname.match(/^\/clients\/\d+\/edit$/)) return 'Edit Client';
    if (pathname.match(/^\/clients\/\d+$/)) return 'Client Details';
    return 'Invoice Machine';
  }

  let pageTitle = $derived(getPageTitle($page.url.pathname));

  let isPublicRoute = $derived(publicRoutes.includes($page.url.pathname));
  let isAuthenticated = $derived($auth.authenticated);
  let needsSetup = $derived($auth.needsSetup);
  let loading = $derived($auth.loading);
  let checkFailed = $derived($auth.checkFailed);

  onMount(async () => {
    await auth.check();
  });

  $effect(() => {
    if (!loading && !checkFailed) {
      const path = $page.url.pathname;

      if (needsSetup && path !== '/setup') {
        goto('/setup');
      } else if (!needsSetup && !isAuthenticated && !publicRoutes.includes(path)) {
        goto('/login');
      } else if (isAuthenticated && publicRoutes.includes(path)) {
        goto('/');
      }
    }
  });
</script>

<svelte:head>
  <title>{pageTitle} - Invoice Machine</title>
</svelte:head>

{#if loading}
  <div class="loading-screen">
    <div class="spinner"></div>
  </div>
{:else if checkFailed}
  <div class="loading-screen">
    <div class="unreachable">
      <p>Could not reach Invoice Machine.</p>
      <button type="button" class="btn btn-secondary" onclick={() => auth.check()}>Try again</button>
    </div>
  </div>
{:else if isPublicRoute}
  {@render children?.()}
  <Toast />
{:else if isAuthenticated}
  <div class="app-layout">
    <Sidebar />
    <main class="main-content">
      {@render children?.()}
    </main>
  </div>
  <Toast />
{/if}

<style>
  .loading-screen {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg);
  }

  .app-layout {
    min-height: 100vh;
  }

  .main-content {
    margin-left: var(--sidebar-width);
    min-height: 100vh;
    background: var(--color-bg);
  }

  .unreachable {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    color: var(--color-text-muted, #6b7280);
  }

  @media (max-width: 768px) {
    .main-content {
      margin-left: 0;
    }
  }
</style>
