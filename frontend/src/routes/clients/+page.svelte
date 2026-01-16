<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { clientsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let clients = [];
  let loading = true;
  let searchQuery = '';

  onMount(async () => {
    await loadClients();
  });

  async function loadClients() {
    loading = true;
    try {
      const params = {};
      if (searchQuery) params.search = searchQuery;
      clients = await clientsApi.list(params);
    } catch (error) {
      toast.error('Failed to load clients');
    } finally {
      loading = false;
    }
  }

  async function deleteClient(e, id, name) {
    e.stopPropagation();
    if (!confirm(`Move "${name}" to trash?`)) return;

    try {
      await clientsApi.delete(id);
      toast.success('Client moved to trash');
      await loadClients();
    } catch (error) {
      toast.error('Failed to delete client');
    }
  }
</script>

<Header title="Clients" />

<div class="page-content">
  <div class="page-header">
    <div class="page-header-text">
      <h1>Clients</h1>
      <p class="page-subtitle">{clients.length} client{clients.length !== 1 ? 's' : ''}</p>
    </div>
    <a href="/clients/new" class="btn btn-primary">
      <Icon name="plus" size="sm" />
      New Client
    </a>
  </div>

  <!-- Search -->
  <div class="search-bar">
    <div class="search-input-wrapper">
      <Icon name="search" size="md" />
      <input
        type="text"
        class="search-input"
        placeholder="Search clients..."
        bind:value={searchQuery}
        on:keydown={(e) => {
          if (e.key === 'Enter') loadClients();
        }}
      />
      {#if searchQuery}
        <button
          class="btn btn-ghost btn-icon btn-sm"
          on:click={() => { searchQuery = ''; loadClients(); }}
        >
          <Icon name="x" size="sm" />
        </button>
      {/if}
    </div>
    <button class="btn btn-secondary" on:click={loadClients}>Search</button>
  </div>

  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else if clients.length > 0}
    <div class="clients-grid">
      {#each clients as client}
        <div class="client-card" on:click={() => goto(`/clients/${client.id}`)} role="button" tabindex="0" on:keydown={(e) => e.key === 'Enter' && goto(`/clients/${client.id}`)}>
          <div class="client-card-header">
            <div class="client-avatar">
              {(client.business_name || client.name || '?').charAt(0).toUpperCase()}
            </div>
            <div class="client-identity">
              <h3 class="client-name">{client.business_name || client.name}</h3>
              {#if client.business_name && client.name}
                <p class="client-contact">{client.name}</p>
              {/if}
            </div>
            <div class="client-actions">
              <button
                class="btn btn-ghost btn-icon btn-sm"
                on:click={(e) => { e.stopPropagation(); goto(`/clients/${client.id}/edit`); }}
                title="Edit"
              >
                <Icon name="pencil" size="sm" />
              </button>
              <button
                class="btn btn-ghost btn-icon btn-sm"
                on:click={(e) => deleteClient(e, client.id, client.business_name || client.name)}
                title="Delete"
              >
                <Icon name="trash" size="sm" />
              </button>
            </div>
          </div>

          <div class="client-details">
            {#if client.email}
              <div class="client-field">
                <Icon name="mail" size="sm" />
                <span>{client.email}</span>
              </div>
            {/if}

            {#if client.phone}
              <div class="client-field">
                <Icon name="phone" size="sm" />
                <span>{client.phone}</span>
              </div>
            {/if}

            {#if client.city || client.state}
              <div class="client-field">
                <Icon name="location" size="sm" />
                <span>{[client.city, client.state].filter(Boolean).join(', ')}</span>
              </div>
            {/if}
          </div>

          <div class="client-footer">
            <span class="payment-terms">Net {client.payment_terms_days || 30} days</span>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty-state">
      <div class="empty-state-icon">
        <Icon name="users" size="xl" />
      </div>
      <div class="empty-state-title">
        {searchQuery ? 'No clients found' : 'No clients yet'}
      </div>
      <div class="empty-state-description">
        {#if searchQuery}
          Try a different search term or create a new client.
        {:else}
          Add your first client to start creating invoices.
        {/if}
      </div>
      <button class="btn btn-primary mt-6" on:click={() => goto('/clients/new')}>
        <Icon name="plus" size="sm" />
        Add Client
      </button>
    </div>
  {/if}
</div>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 1400px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-6);
    gap: var(--space-4);
  }

  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .page-subtitle {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    margin: var(--space-1) 0 0 0;
  }

  .search-bar {
    display: flex;
    gap: var(--space-3);
    margin-bottom: var(--space-6);
  }

  .search-input-wrapper {
    flex: 1;
    max-width: 400px;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-3);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  }

  .search-input-wrapper:focus-within {
    border-color: var(--color-border-focus);
    box-shadow: 0 0 0 3px rgb(59 130 246 / 0.1);
  }

  .search-input-wrapper :global(.icon) {
    color: var(--color-text-tertiary);
  }

  .search-input {
    flex: 1;
    padding: var(--space-2) 0;
    border: none;
    background: none;
    font-size: 0.9375rem;
    color: var(--color-text);
  }

  .search-input:focus {
    outline: none;
  }

  .search-input::placeholder {
    color: var(--color-text-tertiary);
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .clients-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: var(--space-5);
  }

  .client-card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .client-card:hover {
    border-color: var(--color-border);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
  }

  .client-card-header {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }

  .client-avatar {
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-primary-light);
    color: var(--color-primary);
    font-weight: 600;
    font-size: 1.125rem;
    border-radius: var(--radius-md);
    flex-shrink: 0;
  }

  .client-identity {
    flex: 1;
    min-width: 0;
  }

  .client-name {
    font-size: 1.0625rem;
    font-weight: 600;
    margin: 0 0 var(--space-1) 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .client-contact {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin: 0;
  }

  .client-actions {
    display: flex;
    gap: var(--space-1);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .client-card:hover .client-actions {
    opacity: 1;
  }

  .client-details {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--color-border-light);
    margin-bottom: var(--space-3);
  }

  .client-field {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .client-field :global(.icon) {
    color: var(--color-text-tertiary);
  }

  .client-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .payment-terms {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    background: var(--color-bg-sunken);
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-full);
  }

  /* Large screens */
  @media (min-width: 1400px) {
    .clients-grid {
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: var(--space-6);
    }

    .client-card {
      padding: var(--space-6);
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .search-bar {
      flex-direction: column;
    }

    .search-input-wrapper {
      max-width: none;
    }

    .clients-grid {
      grid-template-columns: 1fr;
    }

    .client-actions {
      opacity: 1;
    }
  }

  /* Small screens */
  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .clients-grid {
      gap: var(--space-3);
    }

    .client-card {
      padding: var(--space-4);
    }

    .client-avatar {
      width: 36px;
      height: 36px;
      font-size: 1rem;
    }

    .client-name {
      font-size: 0.9375rem;
    }

    .client-field {
      font-size: 0.8125rem;
    }
  }
</style>
