<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import Toast from '$lib/components/Toast.svelte';

  // Auth-free routes
  const publicRoutes = ['/login', '/setup'];

  // Page titles based on route
  const pageTitles = {
    '/': 'Dashboard',
    '/dashboard': 'Dashboard',
    '/invoices': 'Invoices',
    '/invoices/new': 'New Invoice',
    '/clients': 'Clients',
    '/clients/new': 'New Client',
    '/settings': 'Settings',
    '/trash': 'Trash',
    '/help': 'Help',
  };

  function getPageTitle(pathname) {
    // Check exact match first
    if (pageTitles[pathname]) return pageTitles[pathname];
    // Check for invoice detail/edit
    if (pathname.match(/^\/invoices\/\d+\/edit$/)) return 'Edit Invoice';
    if (pathname.match(/^\/invoices\/\d+$/)) return 'Invoice Details';
    // Check for client detail/edit
    if (pathname.match(/^\/clients\/\d+\/edit$/)) return 'Edit Client';
    if (pathname.match(/^\/clients\/\d+$/)) return 'Client Details';
    return 'Invoice Machine';
  }

  $: pageTitle = getPageTitle($page.url.pathname);

  $: isPublicRoute = publicRoutes.includes($page.url.pathname);
  $: isAuthenticated = $auth.authenticated;
  $: needsSetup = $auth.needsSetup;
  $: loading = $auth.loading;

  onMount(async () => {
    await auth.check();
  });

  // Reactive navigation based on auth state
  $: if (!loading) {
    const path = $page.url.pathname;

    if (needsSetup && path !== '/setup') {
      goto('/setup');
    } else if (!needsSetup && !isAuthenticated && !publicRoutes.includes(path)) {
      goto('/login');
    } else if (isAuthenticated && publicRoutes.includes(path)) {
      goto('/');
    }
  }
</script>

<svelte:head>
  <title>{pageTitle} - Invoice Machine</title>
</svelte:head>

{#if loading}
  <div class="loading-screen">
    <div class="spinner"></div>
  </div>
{:else if isPublicRoute}
  <slot />
  <Toast />
{:else if isAuthenticated}
  <div class="app-layout">
    <Sidebar />
    <main class="main-content">
      <slot />
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

  @media (max-width: 768px) {
    .main-content {
      margin-left: 0;
    }
  }
</style>
