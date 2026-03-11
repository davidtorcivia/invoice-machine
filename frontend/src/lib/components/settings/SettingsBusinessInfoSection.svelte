<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  export let open = false;
  export let name = '';
  export let businessName = '';
  export let email = '';
  export let phone = '';
  export let ein = '';
</script>

<CollapsibleSection title="Business Information" subtitle="Your company details" icon="users" bind:open={open}>
  <div class="form-row">
    <div class="form-group">
      <label for="name" class="label">Your Name *</label>
      <input id="name" type="text" class="input" placeholder="Your name" bind:value={name} />
    </div>

    <div class="form-group">
      <label for="business-name" class="label">Business Name</label>
      <input id="business-name" type="text" class="input" placeholder="Business name or LLC" bind:value={businessName} />
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="email" class="label">Email</label>
      <input id="email" type="email" class="input" placeholder="you@example.com" bind:value={email} />
    </div>

    <div class="form-group">
      <label for="phone" class="label">Phone</label>
      <input id="phone" type="tel" class="input" placeholder="(555) 123-4567" bind:value={phone} />
    </div>
  </div>

  <div class="form-group">
    <label for="ein" class="label">Tax ID / EIN</label>
    <input id="ein" type="text" class="input" placeholder="XX-XXXXXXX" bind:value={ein} />
    <p class="form-hint">Optional. Will appear on invoices if provided.</p>
  </div>
</CollapsibleSection>

<style>
  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }
</style>
