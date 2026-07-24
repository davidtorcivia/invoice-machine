<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import { currencies } from "$lib/data/currencies";

  /** @type {{ base_currency_code: string, rates: Record<string, string> }} */
  export let fxRates = { base_currency_code: 'USD', rates: {} };

  let newCurrency = 'EUR';
  let newRate = '';

  $: entries = Object.entries(fxRates.rates || {}).sort(([a], [b]) => a.localeCompare(b));
  $: available = (currencies || []).filter(
    (currency) => currency.code !== fxRates.base_currency_code
  );

  function addRate() {
    const rate = parseFloat(newRate);
    if (!newCurrency || !(rate > 0)) return;
    fxRates.rates = { ...fxRates.rates, [newCurrency.toUpperCase()]: String(rate) };
    newRate = '';
  }

  function removeRate(code) {
    const { [code]: _removed, ...rest } = fxRates.rates;
    fxRates.rates = rest;
  }
</script>

<CollapsibleSection
  title="Exchange rates"
  subtitle="Convert foreign-currency invoices for consolidated reporting"
>
  <p class="hint">
    Per-currency totals are always reported separately and are never added
    together. These rates power the optional single-currency roll-up on the
    reports page, converting into your base currency
    <strong>{fxRates.base_currency_code}</strong>.
  </p>
  <p class="hint">
    A rate is copied onto each invoice when it is issued, so past invoices keep
    the rate that applied at the time. Changing a rate here affects new invoices
    only.
  </p>

  {#if entries.length === 0}
    <p class="hint">No rates configured. Invoices in other currencies stay out of the roll-up.</p>
  {:else}
    <ul class="rate-list">
      {#each entries as [code, rate] (code)}
        <li class="rate">
          <span class="rate-desc">
            1 {code} = {rate} {fxRates.base_currency_code}
          </span>
          <button
            type="button"
            class="btn-danger-text"
            on:click={() => removeRate(code)}
            aria-label="Remove {code} rate"
          >Remove</button>
        </li>
      {/each}
    </ul>
  {/if}

  <div class="add-row">
    <label class="visually-hidden" for="fx-currency">Currency</label>
    <select id="fx-currency" bind:value={newCurrency} class="select">
      {#each available as currency (currency.code)}
        <option value={currency.code}>{currency.code} - {currency.name}</option>
      {/each}
    </select>

    <label class="visually-hidden" for="fx-rate">Rate</label>
    <input
      id="fx-rate"
      bind:value={newRate}
      type="number"
      step="0.0001"
      min="0"
      class="input"
      placeholder="1.0850"
    />

    <button type="button" class="btn btn-secondary btn-sm" on:click={addRate}>Add</button>
  </div>
</CollapsibleSection>

<style>
  .hint {
    margin: 0 0 0.6rem;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    line-height: 1.5;
  }

  .rate-list {
    list-style: none;
    margin: 0 0 0.75rem;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .rate {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    font-size: 0.88rem;
  }

  .rate-desc {
    font-variant-numeric: tabular-nums;
  }

  .add-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .add-row .select {
    max-width: 220px;
  }

  .add-row .input {
    max-width: 140px;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
</style>
