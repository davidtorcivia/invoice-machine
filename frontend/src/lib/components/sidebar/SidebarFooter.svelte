<script>
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores';
  import Icon from '../Icons.svelte';
  import ThemeToggle from '../ThemeToggle.svelte';

  async function handleLogout() {
    await auth.logout();
    goto('/login');
  }
</script>

<div class="sidebar-footer">
  <ThemeToggle />
  <button class="logout-btn" onclick={handleLogout}>
    <Icon name="logout" size="sm" />
    <span>Sign Out</span>
  </button>
</div>

<style>
  .sidebar-footer {
    padding: var(--space-4) var(--space-6);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .logout-btn {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-3) var(--space-3);
    background: none;
    border: 1px solid color-mix(in srgb, var(--color-danger) 30%, var(--color-border));
    border-radius: var(--radius-md);
    color: color-mix(in srgb, var(--color-danger) 70%, var(--color-text-secondary));
    font-size: 0.875rem;
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .logout-btn:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
    background: var(--color-danger-light);
  }

  @media (max-width: 768px) {
    .sidebar-footer {
      padding-top: var(--space-6);
    }
  }
</style>
