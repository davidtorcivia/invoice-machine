<script>
  import Icon from '$lib/components/Icons.svelte';

  export let show = false;
  export let saving = false;
  export let draft;
  export let close;
  export let save;

  function handleKeydown(event) {
    if (event.key === 'Escape') {
      close();
    }
  }
</script>

{#if show}
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={handleKeydown}>
    <button type="button" class="modal-backdrop" aria-label="Close create client dialog" on:click={close}></button>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1">
      <div class="modal-header">
        <h2 id="modal-title" class="modal-title">New Client</h2>
        <button class="btn btn-ghost btn-icon btn-sm" aria-label="Close" on:click={close}>
          <Icon name="x" size="md" />
        </button>
      </div>

      <div class="modal-body">
        <div class="form-row">
          <div class="form-group">
            <label for="client-name" class="label">Contact Name</label>
            <input id="client-name" type="text" class="input" placeholder="John Smith" bind:value={draft.name} />
          </div>

          <div class="form-group">
            <label for="client-business" class="label">Business Name</label>
            <input id="client-business" type="text" class="input" placeholder="Acme Inc." bind:value={draft.business_name} />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="client-email" class="label">Email</label>
            <input id="client-email" type="email" class="input" placeholder="john@example.com" bind:value={draft.email} />
          </div>

          <div class="form-group">
            <label for="client-phone" class="label">Phone</label>
            <input id="client-phone" type="tel" class="input" placeholder="(555) 123-4567" bind:value={draft.phone} />
          </div>
        </div>

        <div class="form-group">
          <label for="client-address" class="label">Street Address</label>
          <input id="client-address" type="text" class="input" placeholder="123 Main St" bind:value={draft.address_line1} />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="client-city" class="label">City</label>
            <input id="client-city" type="text" class="input" bind:value={draft.city} />
          </div>

          <div class="form-group">
            <label for="client-state" class="label">State</label>
            <input id="client-state" type="text" class="input" bind:value={draft.state} />
          </div>

          <div class="form-group">
            <label for="client-postal" class="label">ZIP Code</label>
            <input id="client-postal" type="text" class="input" bind:value={draft.postal_code} />
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" on:click={close} disabled={saving}>Cancel</button>
        <button type="button" class="btn btn-primary" on:click={save} disabled={saving}>
          {saving ? 'Creating...' : 'Create Client'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }

  :global(.modal) {
    position: relative;
  }
</style>
