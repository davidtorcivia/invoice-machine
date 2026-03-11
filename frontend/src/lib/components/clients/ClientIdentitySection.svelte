<script>
  export let title = 'Client Information';
  export let name = '';
  export let businessName = '';
  export let email = '';
  export let phone = '';
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">{title}</h3>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="business-name" class="label">Business Name</label>
      <input id="business-name" type="text" class="input" placeholder="Company name" bind:value={businessName} />
    </div>

    <div class="form-group">
      <label for="name" class="label">Contact Name</label>
      <input id="name" type="text" class="input" placeholder="Primary contact" bind:value={name} />
    </div>
  </div>

  <div class="form-row">
    <div class="form-group">
      <label for="email" class="label">Email</label>
      <input id="email" type="email" class="input" placeholder="contact@example.com" bind:value={email} />
    </div>

    <div class="form-group">
      <label for="phone" class="label">Phone</label>
      <input id="phone" type="tel" class="input" placeholder="(555) 123-4567" bind:value={phone} />
    </div>
  </div>
</div>
