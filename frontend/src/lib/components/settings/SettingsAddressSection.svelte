<script lang="ts">
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  interface Props {
    open?: boolean;
    addressLine1?: string;
    addressLine2?: string;
    city?: string;
    state?: string;
    postalCode?: string;
    country?: string;
    countries?: any;
  }

  let {
    open = $bindable(false),
    addressLine1 = $bindable(''),
    addressLine2 = $bindable(''),
    city = $bindable(''),
    state = $bindable(''),
    postalCode = $bindable(''),
    country = $bindable(''),
    countries = []
  }: Props = $props();
</script>

<CollapsibleSection title="Business Address" subtitle="Your mailing address" icon="home" bind:open={open}>
  <div class="form-group">
    <label for="address1" class="label">Street Address</label>
    <input id="address1" type="text" class="input" placeholder="123 Main St" bind:value={addressLine1} />
  </div>

  <div class="form-group">
    <label for="address2" class="label">Apartment, suite, etc.</label>
    <input id="address2" type="text" class="input" placeholder="Apt 4" bind:value={addressLine2} />
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="city" class="label">City</label>
      <input id="city" type="text" class="input" placeholder="City" bind:value={city} />
    </div>

    <div class="form-group">
      <label for="state" class="label">State</label>
      <input id="state" type="text" class="input" placeholder="State" bind:value={state} />
    </div>

    <div class="form-group">
      <label for="postal" class="label">ZIP Code</label>
      <input id="postal" type="text" class="input" placeholder="12345" bind:value={postalCode} />
    </div>
  </div>

  <div class="form-group">
    <label for="country" class="label">Country</label>
    <select id="country" class="select" bind:value={country}>
      <option value="">Select a country...</option>
      {#each countries as value}
        <option value={value}>{value}</option>
      {/each}
    </select>
  </div>
</CollapsibleSection>
