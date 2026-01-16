<script>
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/dashboard', { replaceState: true });
  });
</script>

<div class="redirect-container">
  <div class="spinner"></div>
</div>

<style>
  .redirect-container {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
  }
</style>
