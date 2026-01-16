<script>
  import { onMount } from 'svelte';
  import { profileApi, backupsApi } from '$lib/api';
  import { toast } from '$lib/stores';
  import { countries } from '$lib/data/countries';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';

  let profile = null;
  let loading = true;
  let saving = false;

  // Form data
  let name = '';
  let businessName = '';
  let email = '';
  let phone = '';
  let addressLine1 = '';
  let addressLine2 = '';
  let city = '';
  let state = '';
  let postalCode = '';
  let country = 'United States';
  let ein = '';
  let accentColor = '#16a34a';
  let defaultPaymentTermsDays = 30;
  let defaultNotes = '';
  let defaultPaymentInstructions = '';

  // Payment methods (array of {id, name, instructions})
  let paymentMethods = [];
  let editingMethod = null;
  let newMethodName = '';
  let newMethodInstructions = '';
  let showPaymentMethodModal = false;

  // Logo upload
  let logoPreview = null;
  let logoUploading = false;
  let uploadProgress = 0;
  let showDeleteLogoModal = false;
  let deletingLogo = false;

  // MCP Integration
  let mcpApiKey = '';
  let appBaseUrl = '';
  let generatingMcpKey = false;
  let showMcpKeyModal = false;

  // Computed MCP endpoint URL
  $: mcpEndpointUrl = appBaseUrl || (typeof window !== 'undefined' ? window.location.origin : '');

  // Backup settings
  let backupEnabled = true;
  let backupRetentionDays = 30;
  let backupS3Enabled = false;
  let backupS3EndpointUrl = '';
  let backupS3AccessKeyId = '';
  let backupS3SecretAccessKey = '';
  let backupS3Bucket = '';
  let backupS3Region = '';
  let backupS3Prefix = 'invoice-machine-backups';
  let backups = [];
  let loadingBackups = false;
  let creatingBackup = false;
  let restoringBackup = null;
  let testingS3 = false;
  let showRestoreModal = false;
  let restoreTarget = null;

  onMount(async () => {
    await loadProfile();
    await loadBackupSettings();
    await loadBackups();
  });

  async function loadProfile() {
    loading = true;
    try {
      profile = await profileApi.get();

      // Populate form
      name = profile.name || '';
      businessName = profile.business_name || '';
      email = profile.email || '';
      phone = profile.phone || '';
      addressLine1 = profile.address_line1 || '';
      addressLine2 = profile.address_line2 || '';
      city = profile.city || '';
      state = profile.state || '';
      postalCode = profile.postal_code || '';
      country = profile.country || 'United States';
      ein = profile.ein || '';
      accentColor = profile.accent_color || '#16a34a';
      defaultPaymentTermsDays = profile.default_payment_terms_days || 30;
      defaultNotes = profile.default_notes || '';
      defaultPaymentInstructions = profile.default_payment_instructions || '';

      // Parse payment methods from JSON
      try {
        paymentMethods = profile.payment_methods ? JSON.parse(profile.payment_methods) : [];
      } catch {
        paymentMethods = [];
      }

      if (profile.logo_path) {
        logoPreview = `/api/profile/logo/${profile.logo_path}`;
      }

      // MCP settings
      mcpApiKey = profile.mcp_api_key || '';
      appBaseUrl = profile.app_base_url || '';
    } catch (error) {
      toast.error('Failed to load profile');
    } finally {
      loading = false;
    }
  }

  async function saveProfile() {
    if (!name.trim()) {
      toast.error('Please enter your name');
      return;
    }

    saving = true;
    try {
      await profileApi.update({
        name: name || undefined,
        business_name: businessName || undefined,
        email: email || undefined,
        phone: phone || undefined,
        address_line1: addressLine1 || undefined,
        address_line2: addressLine2 || undefined,
        city: city || undefined,
        state: state || undefined,
        postal_code: postalCode || undefined,
        country: country || undefined,
        ein: ein || undefined,
        accent_color: accentColor || undefined,
        default_payment_terms_days: parseInt(defaultPaymentTermsDays) || undefined,
        default_notes: defaultNotes || undefined,
        default_payment_instructions: defaultPaymentInstructions || undefined,
        payment_methods: JSON.stringify(paymentMethods),
        app_base_url: appBaseUrl || undefined,
      });

      toast.success('Settings saved successfully');
    } catch (error) {
      toast.error('Failed to save settings');
    } finally {
      saving = false;
    }
  }

  async function handleLogoSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file');
      return;
    }

    // Validate file size (5MB max)
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be less than 5MB');
      return;
    }

    // Start upload immediately
    logoUploading = true;
    uploadProgress = 0;

    try {
      // Simulate progress for better UX
      const progressInterval = setInterval(() => {
        if (uploadProgress < 90) {
          uploadProgress += Math.random() * 20;
        }
      }, 100);

      const result = await profileApi.uploadLogo(file);

      clearInterval(progressInterval);
      uploadProgress = 100;

      // Short delay to show 100% before hiding
      await new Promise(resolve => setTimeout(resolve, 300));

      logoPreview = `/api/profile/logo/${result.logo_path}`;
      toast.success('Logo uploaded successfully');
    } catch (error) {
      toast.error('Failed to upload logo');
    } finally {
      logoUploading = false;
      uploadProgress = 0;
      // Reset input so same file can be selected again
      event.target.value = '';
    }
  }

  function openDeleteLogoModal() {
    showDeleteLogoModal = true;
  }

  function closeDeleteLogoModal() {
    showDeleteLogoModal = false;
  }

  async function deleteLogo() {
    deletingLogo = true;
    try {
      await profileApi.deleteLogo();
      logoPreview = null;
      toast.success('Logo deleted');
      closeDeleteLogoModal();
    } catch (error) {
      toast.error('Failed to delete logo');
    } finally {
      deletingLogo = false;
    }
  }

  // Payment method functions
  function openAddMethodModal() {
    editingMethod = null;
    newMethodName = '';
    newMethodInstructions = '';
    showPaymentMethodModal = true;
  }

  function openEditMethodModal(method) {
    editingMethod = method;
    newMethodName = method.name;
    newMethodInstructions = method.instructions;
    showPaymentMethodModal = true;
  }

  function closePaymentMethodModal() {
    showPaymentMethodModal = false;
    editingMethod = null;
    newMethodName = '';
    newMethodInstructions = '';
  }

  function savePaymentMethod() {
    if (!newMethodName.trim()) {
      toast.error('Please enter a method name');
      return;
    }

    if (editingMethod) {
      // Update existing
      paymentMethods = paymentMethods.map(m =>
        m.id === editingMethod.id
          ? { ...m, name: newMethodName.trim(), instructions: newMethodInstructions.trim() }
          : m
      );
    } else {
      // Add new
      const newMethod = {
        id: Date.now().toString(),
        name: newMethodName.trim(),
        instructions: newMethodInstructions.trim()
      };
      paymentMethods = [...paymentMethods, newMethod];
    }

    closePaymentMethodModal();
  }

  function deletePaymentMethod(id) {
    paymentMethods = paymentMethods.filter(m => m.id !== id);
  }

  // MCP functions
  async function generateMcpKey() {
    generatingMcpKey = true;
    try {
      const result = await profileApi.generateMcpKey();
      mcpApiKey = result.mcp_api_key;
      showMcpKeyModal = true;
      toast.success('MCP API key generated');
    } catch (error) {
      toast.error('Failed to generate API key');
    } finally {
      generatingMcpKey = false;
    }
  }

  async function deleteMcpKey() {
    if (!confirm('Are you sure you want to disable remote MCP access? You will need to generate a new key to reconnect.')) {
      return;
    }
    try {
      await profileApi.deleteMcpKey();
      mcpApiKey = '';
      toast.success('MCP API key deleted');
    } catch (error) {
      toast.error('Failed to delete API key');
    }
  }

  function copyMcpKey() {
    navigator.clipboard.writeText(mcpApiKey);
    toast.success('API key copied to clipboard');
  }

  function closeMcpKeyModal() {
    showMcpKeyModal = false;
  }

  // Backup functions
  async function loadBackupSettings() {
    try {
      const settings = await backupsApi.getSettings();
      backupEnabled = settings.backup_enabled;
      backupRetentionDays = settings.backup_retention_days;
      backupS3Enabled = settings.backup_s3_enabled;
      backupS3EndpointUrl = settings.backup_s3_endpoint_url || '';
      backupS3Bucket = settings.backup_s3_bucket || '';
      backupS3Region = settings.backup_s3_region || '';
      backupS3Prefix = settings.backup_s3_prefix || 'invoice-machine-backups';
    } catch (error) {
      // Settings might not exist yet, use defaults
    }
  }

  async function loadBackups() {
    loadingBackups = true;
    try {
      backups = await backupsApi.list(backupS3Enabled);
    } catch (error) {
      backups = [];
    } finally {
      loadingBackups = false;
    }
  }

  async function saveBackupSettings() {
    try {
      const data = {
        backup_enabled: backupEnabled,
        backup_retention_days: parseInt(backupRetentionDays) || 30,
        backup_s3_enabled: backupS3Enabled,
      };

      if (backupS3Enabled) {
        data.backup_s3_endpoint_url = backupS3EndpointUrl || null;
        data.backup_s3_bucket = backupS3Bucket || null;
        data.backup_s3_region = backupS3Region || null;
        data.backup_s3_prefix = backupS3Prefix || null;

        // Only send credentials if they're provided (not masked)
        if (backupS3AccessKeyId && !backupS3AccessKeyId.includes('*')) {
          data.backup_s3_access_key_id = backupS3AccessKeyId;
        }
        if (backupS3SecretAccessKey && !backupS3SecretAccessKey.includes('*')) {
          data.backup_s3_secret_access_key = backupS3SecretAccessKey;
        }
      }

      await backupsApi.updateSettings(data);
      toast.success('Backup settings saved');
    } catch (error) {
      toast.error('Failed to save backup settings');
    }
  }

  async function createBackup() {
    creatingBackup = true;
    try {
      const result = await backupsApi.create(true);
      toast.success(`Backup created: ${result.filename}`);
      await loadBackups();
    } catch (error) {
      toast.error(error.message || 'Failed to create backup');
    } finally {
      creatingBackup = false;
    }
  }

  function openRestoreModal(backup) {
    restoreTarget = backup;
    showRestoreModal = true;
  }

  function closeRestoreModal() {
    showRestoreModal = false;
    restoreTarget = null;
  }

  async function restoreBackup() {
    if (!restoreTarget) return;

    restoringBackup = restoreTarget.filename;
    try {
      const downloadFromS3 = restoreTarget.location === 's3';
      const result = await backupsApi.restore(restoreTarget.filename, downloadFromS3);
      toast.success(result.message);
      closeRestoreModal();
    } catch (error) {
      toast.error(error.message || 'Failed to restore backup');
    } finally {
      restoringBackup = null;
    }
  }

  async function deleteBackup(filename) {
    if (!confirm(`Delete backup ${filename}?`)) return;

    try {
      await backupsApi.delete(filename);
      toast.success('Backup deleted');
      await loadBackups();
    } catch (error) {
      toast.error('Failed to delete backup');
    }
  }

  async function testS3Connection() {
    testingS3 = true;
    try {
      // Save settings first
      await saveBackupSettings();
      const result = await backupsApi.testS3();
      toast.success(result.message);
    } catch (error) {
      toast.error(error.message || 'S3 connection failed');
    } finally {
      testingS3 = false;
    }
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatDate(isoString) {
    return new Date(isoString).toLocaleString();
  }
</script>

<Header title="Settings" subtitle="Manage your business profile and invoice defaults" />

<div class="page-content">
  {#if loading}
    <div class="loading-container">
      <div class="spinner"></div>
    </div>
  {:else}
    <div class="settings-layout">
      <!-- Logo Section -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Logo</h3>
        </div>

        <div class="logo-section">
          <div class="logo-preview" class:has-logo={logoPreview} class:uploading={logoUploading}>
            {#if logoUploading}
              <div class="upload-progress">
                <div class="progress-bar">
                  <div class="progress-fill" style="width: {Math.min(uploadProgress, 100)}%"></div>
                </div>
                <span class="progress-text">Uploading...</span>
              </div>
            {:else if logoPreview}
              <img src={logoPreview} alt="Logo" />
            {:else}
              <div class="logo-placeholder">
                <Icon name="image" size="lg" />
                <span>Your Logo</span>
              </div>
            {/if}
          </div>

          <div class="logo-controls">
            <p class="logo-hint">Upload your company logo. It will appear on invoices and PDFs.</p>
            <div class="logo-buttons">
              <label class="btn btn-secondary" class:disabled={logoUploading}>
                <Icon name="upload" size="sm" />
                {logoPreview ? 'Change Logo' : 'Upload Logo'}
                <input
                  type="file"
                  accept="image/*"
                  on:change={handleLogoSelect}
                  disabled={logoUploading}
                  style="display: none"
                />
              </label>

              {#if logoPreview && !logoUploading}
                <button
                  class="btn btn-ghost btn-danger-text"
                  on:click={openDeleteLogoModal}
                >
                  <Icon name="trash" size="sm" />
                  Delete
                </button>
              {/if}
            </div>
          </div>
        </div>
      </div>

      <!-- Business Info Form -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Business Information</h3>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="name" class="label">Your Name *</label>
            <input
              id="name"
              type="text"
              class="input"
              placeholder="Your name"
              bind:value={name}
            />
          </div>

          <div class="form-group">
            <label for="business-name" class="label">Business Name</label>
            <input
              id="business-name"
              type="text"
              class="input"
              placeholder="Business name or LLC"
              bind:value={businessName}
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="email" class="label">Email</label>
            <input
              id="email"
              type="email"
              class="input"
              placeholder="you@example.com"
              bind:value={email}
            />
          </div>

          <div class="form-group">
            <label for="phone" class="label">Phone</label>
            <input
              id="phone"
              type="tel"
              class="input"
              placeholder="(555) 123-4567"
              bind:value={phone}
            />
          </div>
        </div>

        <div class="form-group">
          <label for="ein" class="label">Tax ID / EIN</label>
          <input
            id="ein"
            type="text"
            class="input"
            placeholder="XX-XXXXXXX"
            bind:value={ein}
          />
          <p class="form-hint">Optional. Will appear on invoices if provided.</p>
        </div>
      </div>

      <!-- Address -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Business Address</h3>
        </div>

        <div class="form-group">
          <label for="address1" class="label">Street Address</label>
          <input
            id="address1"
            type="text"
            class="input"
            placeholder="123 Main St"
            bind:value={addressLine1}
          />
        </div>

        <div class="form-group">
          <label for="address2" class="label">Apartment, suite, etc.</label>
          <input
            id="address2"
            type="text"
            class="input"
            placeholder="Apt 4"
            bind:value={addressLine2}
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="city" class="label">City</label>
            <input
              id="city"
              type="text"
              class="input"
              placeholder="City"
              bind:value={city}
            />
          </div>

          <div class="form-group">
            <label for="state" class="label">State</label>
            <input
              id="state"
              type="text"
              class="input"
              placeholder="State"
              bind:value={state}
            />
          </div>

          <div class="form-group">
            <label for="postal" class="label">ZIP Code</label>
            <input
              id="postal"
              type="text"
              class="input"
              placeholder="12345"
              bind:value={postalCode}
            />
          </div>
        </div>

        <div class="form-group">
          <label for="country" class="label">Country</label>
          <select id="country" class="select" bind:value={country}>
            <option value="">Select a country...</option>
            {#each countries as c}
              <option value={c}>{c}</option>
            {/each}
          </select>
        </div>
      </div>

      <!-- Invoice Defaults -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Invoice Defaults</h3>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="default-terms" class="label">Default Payment Terms (days)</label>
            <input
              id="default-terms"
              type="number"
              class="input"
              min="0"
              bind:value={defaultPaymentTermsDays}
            />
            <p class="form-hint">Default due date for new invoices.</p>
          </div>

          <div class="form-group">
            <label for="accent-color" class="label">Accent Color</label>
            <div class="color-input">
              <input
                id="accent-color"
                type="color"
                class="color-picker"
                bind:value={accentColor}
              />
              <input
                type="text"
                class="input"
                bind:value={accentColor}
                placeholder="#16a34a"
              />
            </div>
            <p class="form-hint">Used for headings and accents on PDFs.</p>
          </div>
        </div>

        <div class="form-group">
          <label for="default-notes" class="label">Default Invoice Notes</label>
          <textarea
            id="default-notes"
            class="textarea"
            rows="3"
            placeholder="Thank you for your business. Payment is due within the terms specified."
            bind:value={defaultNotes}
          ></textarea>
          <p class="form-hint">This text will appear at the bottom of all new invoices.</p>
        </div>

        <div class="form-group">
          <label for="payment-instructions" class="label">Default Payment Instructions (Legacy)</label>
          <textarea
            id="payment-instructions"
            class="textarea"
            rows="4"
            placeholder="Bank: Example Bank&#10;Account: 123456789&#10;Routing: 987654321&#10;&#10;Or pay via PayPal: payments@example.com"
            bind:value={defaultPaymentInstructions}
          ></textarea>
          <p class="form-hint">Fallback text when no payment methods are selected below.</p>
        </div>
      </div>

      <!-- Payment Methods -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Payment Methods</h3>
          <button type="button" class="btn btn-secondary btn-sm" on:click={openAddMethodModal}>
            <Icon name="plus" size="sm" />
            Add Method
          </button>
        </div>

        <p class="form-hint mb-4">Configure payment options your clients can use. Select which methods to show on each invoice.</p>

        {#if paymentMethods.length > 0}
          <div class="payment-methods-list">
            {#each paymentMethods as method}
              <div class="payment-method-item">
                <div class="payment-method-info">
                  <span class="payment-method-name">{method.name}</span>
                  {#if method.instructions}
                    <span class="payment-method-preview">{method.instructions.substring(0, 60)}{method.instructions.length > 60 ? '...' : ''}</span>
                  {/if}
                </div>
                <div class="payment-method-actions">
                  <button class="btn btn-ghost btn-icon btn-sm" on:click={() => openEditMethodModal(method)} title="Edit">
                    <Icon name="pencil" size="sm" />
                  </button>
                  <button class="btn btn-ghost btn-icon btn-sm" on:click={() => deletePaymentMethod(method.id)} title="Delete">
                    <Icon name="trash" size="sm" />
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="empty-methods">
            <p class="text-secondary">No payment methods configured yet.</p>
            <button class="btn btn-secondary btn-sm mt-2" on:click={openAddMethodModal}>
              <Icon name="plus" size="sm" />
              Add your first method
            </button>
          </div>
        {/if}
      </div>

      <!-- MCP Integration -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">MCP Integration (Claude Desktop)</h3>
        </div>

        <p class="form-hint mb-4">
          Enable remote access to Invoice Machine via Claude Desktop using the Model Context Protocol (MCP).
          Generate an API key to allow secure connections from another computer.
        </p>

        <div class="form-group">
          <label for="app-base-url" class="label">Application URL</label>
          <input
            id="app-base-url"
            type="url"
            class="input"
            placeholder="https://invoices.example.com"
            bind:value={appBaseUrl}
          />
          <p class="form-hint">
            Set this to your public URL (e.g., Cloudflare Tunnel URL). Used for MCP connections and PDF links.
            Leave empty to use the current browser URL.
          </p>
        </div>

        {#if mcpApiKey}
          <div class="mcp-status mcp-enabled">
            <div class="mcp-status-icon">
              <Icon name="check" size="md" />
            </div>
            <div class="mcp-status-info">
              <span class="mcp-status-label">Remote access enabled</span>
              <span class="mcp-status-endpoint">Endpoint: <code>{mcpEndpointUrl}/mcp/sse</code></span>
            </div>
          </div>

          <div class="mcp-key-display">
            <label class="label">API Key</label>
            <div class="mcp-key-row">
              <input type="password" class="input" value={mcpApiKey} readonly />
              <button class="btn btn-secondary" on:click={copyMcpKey}>
                <Icon name="copy" size="sm" />
                Copy
              </button>
            </div>
          </div>

          <div class="mcp-actions">
            <button class="btn btn-secondary" on:click={generateMcpKey} disabled={generatingMcpKey}>
              <Icon name="refresh" size="sm" />
              Regenerate Key
            </button>
            <button class="btn btn-ghost btn-danger-text" on:click={deleteMcpKey}>
              <Icon name="trash" size="sm" />
              Disable Remote Access
            </button>
          </div>
        {:else}
          <div class="mcp-status mcp-disabled">
            <div class="mcp-status-icon">
              <Icon name="x" size="md" />
            </div>
            <div class="mcp-status-info">
              <span class="mcp-status-label">Remote access disabled</span>
              <span class="mcp-status-hint">Generate an API key to enable Claude Desktop connections</span>
            </div>
          </div>

          <button class="btn btn-primary" on:click={generateMcpKey} disabled={generatingMcpKey}>
            <Icon name="plus" size="sm" />
            {generatingMcpKey ? 'Generating...' : 'Generate API Key'}
          </button>
        {/if}

        <div class="mcp-help mt-4">
          <details>
            <summary>How to configure Claude Desktop</summary>
            <div class="mcp-help-content">
              <p>Add this to your Claude Desktop config file:</p>
              <pre class="code-block">{`{
  "mcpServers": {
    "invoice-machine": {
      "transport": "sse",
      "url": "${mcpEndpointUrl}/mcp/sse",
      "headers": {
        "Authorization": "Bearer ${mcpApiKey || 'YOUR_API_KEY'}"
      }
    }
  }
}`}</pre>
              <p class="mt-2"><strong>Config file location:</strong></p>
              <ul>
                <li><strong>macOS:</strong> <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></li>
                <li><strong>Windows:</strong> <code>%APPDATA%\Claude\claude_desktop_config.json</code></li>
              </ul>
            </div>
          </details>
        </div>
      </div>

      <!-- Backup & Restore -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Backup & Restore</h3>
          <button
            class="btn btn-secondary btn-sm"
            on:click={createBackup}
            disabled={creatingBackup}
          >
            <Icon name="plus" size="sm" />
            {creatingBackup ? 'Creating...' : 'Create Backup'}
          </button>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="checkbox-label">
              <input type="checkbox" bind:checked={backupEnabled} />
              <span>Enable automatic daily backups</span>
            </label>
          </div>

          <div class="form-group">
            <label for="backup-retention" class="label">Retention (days)</label>
            <input
              id="backup-retention"
              type="number"
              class="input"
              min="1"
              max="365"
              bind:value={backupRetentionDays}
            />
          </div>
        </div>

        <!-- S3 Configuration -->
        <div class="s3-section">
          <label class="checkbox-label mb-3">
            <input type="checkbox" bind:checked={backupS3Enabled} />
            <span>Upload backups to S3-compatible storage</span>
          </label>

          {#if backupS3Enabled}
            <div class="s3-fields">
              <div class="form-group">
                <label for="s3-endpoint" class="label">Endpoint URL (optional)</label>
                <input
                  id="s3-endpoint"
                  type="url"
                  class="input"
                  placeholder="https://s3.amazonaws.com or Backblaze/MinIO URL"
                  bind:value={backupS3EndpointUrl}
                />
                <p class="form-hint">Leave empty for AWS S3, or enter custom endpoint for Backblaze B2, MinIO, etc.</p>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label for="s3-access-key" class="label">Access Key ID</label>
                  <input
                    id="s3-access-key"
                    type="text"
                    class="input"
                    placeholder="AKIAIOSFODNN7EXAMPLE"
                    bind:value={backupS3AccessKeyId}
                  />
                </div>

                <div class="form-group">
                  <label for="s3-secret-key" class="label">Secret Access Key</label>
                  <input
                    id="s3-secret-key"
                    type="password"
                    class="input"
                    placeholder="Enter secret key"
                    bind:value={backupS3SecretAccessKey}
                  />
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label for="s3-bucket" class="label">Bucket Name</label>
                  <input
                    id="s3-bucket"
                    type="text"
                    class="input"
                    placeholder="my-backup-bucket"
                    bind:value={backupS3Bucket}
                  />
                </div>

                <div class="form-group">
                  <label for="s3-region" class="label">Region</label>
                  <input
                    id="s3-region"
                    type="text"
                    class="input"
                    placeholder="us-east-1"
                    bind:value={backupS3Region}
                  />
                </div>
              </div>

              <div class="form-group">
                <label for="s3-prefix" class="label">Path Prefix</label>
                <input
                  id="s3-prefix"
                  type="text"
                  class="input"
                  placeholder="invoice-machine-backups"
                  bind:value={backupS3Prefix}
                />
              </div>

              <button
                class="btn btn-secondary btn-sm"
                on:click={testS3Connection}
                disabled={testingS3}
              >
                {testingS3 ? 'Testing...' : 'Test S3 Connection'}
              </button>
            </div>
          {/if}
        </div>

        <div class="backup-actions mt-4">
          <button class="btn btn-secondary" on:click={saveBackupSettings}>
            <Icon name="check" size="sm" />
            Save Backup Settings
          </button>
        </div>

        <!-- Backup List -->
        <div class="backup-list mt-4">
          <h4 class="backup-list-title">Available Backups</h4>

          {#if loadingBackups}
            <div class="loading-container">
              <div class="spinner"></div>
            </div>
          {:else if backups.length === 0}
            <p class="text-secondary">No backups yet. Create one using the button above.</p>
          {:else}
            <div class="backup-items">
              {#each backups as backup}
                <div class="backup-item">
                  <div class="backup-info">
                    <span class="backup-filename">{backup.filename}</span>
                    <span class="backup-meta">
                      {formatBytes(backup.size_bytes)} | {formatDate(backup.created_at)}
                      {#if backup.location === 's3'}
                        <span class="backup-location">S3</span>
                      {/if}
                    </span>
                  </div>
                  <div class="backup-item-actions">
                    {#if backup.location === 'local'}
                      <a
                        href={backupsApi.download(backup.filename)}
                        class="btn btn-ghost btn-icon btn-sm"
                        title="Download"
                        download
                      >
                        <Icon name="download" size="sm" />
                      </a>
                    {/if}
                    <button
                      class="btn btn-ghost btn-icon btn-sm"
                      on:click={() => openRestoreModal(backup)}
                      title="Restore"
                      disabled={restoringBackup === backup.filename}
                    >
                      <Icon name="refresh" size="sm" />
                    </button>
                    {#if backup.location === 'local'}
                      <button
                        class="btn btn-ghost btn-icon btn-sm"
                        on:click={() => deleteBackup(backup.filename)}
                        title="Delete"
                      >
                        <Icon name="trash" size="sm" />
                      </button>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      <!-- Save Button -->
      <div class="form-actions">
        <button
          type="button"
          class="btn btn-primary"
          on:click={saveProfile}
          disabled={saving}
        >
          <Icon name="check" size="sm" />
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  {/if}
</div>

<!-- Delete Logo Confirmation Modal -->
{#if showDeleteLogoModal}
  <div class="modal-overlay" on:click={closeDeleteLogoModal} on:keydown={(e) => e.key === 'Escape' && closeDeleteLogoModal()}>
    <div class="modal modal-sm" on:click|stopPropagation role="dialog" aria-modal="true">
      <div class="modal-icon modal-icon-danger">
        <Icon name="trash" size="lg" />
      </div>
      <h2 class="modal-title">Delete Logo?</h2>
      <p class="modal-message">This will remove your logo from all invoices. This action cannot be undone.</p>
      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={closeDeleteLogoModal} disabled={deletingLogo}>
          Cancel
        </button>
        <button class="btn btn-danger" on:click={deleteLogo} disabled={deletingLogo}>
          {deletingLogo ? 'Deleting...' : 'Delete Logo'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Restore Backup Confirmation Modal -->
{#if showRestoreModal && restoreTarget}
  <div class="modal-overlay" on:click={closeRestoreModal} on:keydown={(e) => e.key === 'Escape' && closeRestoreModal()}>
    <div class="modal modal-sm" on:click|stopPropagation role="dialog" aria-modal="true">
      <div class="modal-icon modal-icon-warning">
        <Icon name="refresh" size="lg" />
      </div>
      <h2 class="modal-title">Restore Backup?</h2>
      <p class="modal-message">
        This will overwrite your current database with <strong>{restoreTarget.filename}</strong>.
        A pre-restore backup will be created automatically.
        <br /><br />
        <strong>The application will need to be restarted after restore.</strong>
      </p>
      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={closeRestoreModal} disabled={restoringBackup}>
          Cancel
        </button>
        <button class="btn btn-primary" on:click={restoreBackup} disabled={restoringBackup}>
          {restoringBackup ? 'Restoring...' : 'Restore Backup'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Payment Method Modal -->
{#if showPaymentMethodModal}
  <div class="modal-overlay" on:click={closePaymentMethodModal} on:keydown={(e) => e.key === 'Escape' && closePaymentMethodModal()}>
    <div class="modal" on:click|stopPropagation role="dialog" aria-modal="true">
      <div class="modal-header">
        <h2 class="modal-title">{editingMethod ? 'Edit Payment Method' : 'Add Payment Method'}</h2>
        <button class="btn btn-ghost btn-icon btn-sm" on:click={closePaymentMethodModal}>
          <Icon name="x" size="md" />
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="method-name" class="label">Method Name *</label>
          <input
            id="method-name"
            type="text"
            class="input"
            placeholder="e.g., Bank Transfer (ACH), Venmo, Zelle"
            bind:value={newMethodName}
          />
        </div>
        <div class="form-group">
          <label for="method-instructions" class="label">Payment Details</label>
          <textarea
            id="method-instructions"
            class="textarea"
            rows="5"
            placeholder="Enter the payment details your clients will need, e.g.:&#10;Bank: Example Bank&#10;Account: 123456789&#10;Routing: 987654321"
            bind:value={newMethodInstructions}
          ></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" on:click={closePaymentMethodModal}>Cancel</button>
        <button class="btn btn-primary" on:click={savePaymentMethod}>
          {editingMethod ? 'Save Changes' : 'Add Method'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 800px;
  }

  .loading-container {
    display: flex;
    justify-content: center;
    padding: var(--space-12);
  }

  .settings-layout {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  /* Logo Section */
  .logo-section {
    display: flex;
    gap: var(--space-6);
    align-items: flex-start;
  }

  .logo-preview {
    width: 160px;
    height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-sunken);
    border: 2px dashed var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    flex-shrink: 0;
    position: relative;
  }

  .logo-preview.has-logo {
    border-style: solid;
    background: var(--color-bg);
  }

  .logo-preview.uploading {
    border-color: var(--color-primary);
    background: var(--color-primary-light);
  }

  .logo-preview img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .logo-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-text-tertiary);
    font-size: 0.8125rem;
  }

  .upload-progress {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    width: 80%;
  }

  .progress-bar {
    width: 100%;
    height: 4px;
    background: var(--color-bg);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--color-primary);
    transition: width 0.1s ease;
  }

  .progress-text {
    font-size: 0.75rem;
    color: var(--color-primary);
    font-weight: 500;
  }

  .logo-controls {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .logo-hint {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    line-height: 1.5;
  }

  .logo-buttons {
    display: flex;
    gap: var(--space-2);
  }

  .btn.disabled {
    opacity: 0.5;
    pointer-events: none;
  }

  .btn-danger-text {
    color: var(--color-danger);
  }

  .btn-danger-text:hover:not(:disabled) {
    background: var(--color-danger-light);
    color: var(--color-danger);
  }

  /* Color Input */
  .color-input {
    display: flex;
    gap: var(--space-2);
  }

  .color-picker {
    width: 48px;
    height: 42px;
    padding: var(--space-1);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    cursor: pointer;
    background: var(--color-bg);
  }

  .color-picker::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  .color-picker::-webkit-color-swatch {
    border: none;
    border-radius: var(--radius-sm);
  }

  .color-input .input {
    flex: 1;
  }

  .form-hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin-top: var(--space-1);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
  }

  /* Delete Modal */
  .modal-sm {
    max-width: 360px;
    text-align: center;
    padding: var(--space-8);
  }

  .modal-icon {
    width: 56px;
    height: 56px;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto var(--space-4);
  }

  .modal-icon-danger {
    background: var(--color-danger-light);
    color: var(--color-danger);
  }

  .modal-sm .modal-title {
    font-size: 1.125rem;
    margin-bottom: var(--space-2);
  }

  .modal-message {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin-bottom: var(--space-6);
    line-height: 1.5;
  }

  .modal-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: center;
  }

  /* Payment Methods */
  .mb-4 {
    margin-bottom: var(--space-4);
  }

  .mt-2 {
    margin-top: var(--space-2);
  }

  .payment-methods-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .payment-method-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3) var(--space-4);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    gap: var(--space-3);
  }

  .payment-method-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
    flex: 1;
  }

  .payment-method-name {
    font-weight: 500;
    color: var(--color-text);
  }

  .payment-method-preview {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .payment-method-actions {
    display: flex;
    gap: var(--space-1);
    flex-shrink: 0;
  }

  .empty-methods {
    text-align: center;
    padding: var(--space-4);
  }

  /* Large screens */
  @media (min-width: 1400px) {
    .page-content {
      max-width: 900px;
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }

    .logo-section {
      flex-direction: column;
    }

    .logo-preview {
      width: 100%;
      max-width: 200px;
    }

    .logo-buttons {
      flex-direction: column;
    }

    .color-input {
      flex-direction: column;
    }

    .color-picker {
      width: 100%;
      height: 48px;
    }
  }

  /* Small screens */
  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .modal-sm {
      padding: var(--space-6);
    }

    .modal-actions {
      flex-direction: column-reverse;
    }

    .modal-actions .btn {
      width: 100%;
    }

    .form-actions .btn {
      width: 100%;
    }
  }

  /* MCP Integration */
  .mcp-status {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-4);
  }

  .mcp-enabled {
    background: var(--color-success-light);
  }

  .mcp-disabled {
    background: var(--color-bg-sunken);
  }

  .mcp-status-icon {
    width: 40px;
    height: 40px;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .mcp-enabled .mcp-status-icon {
    background: var(--color-success);
    color: white;
  }

  .mcp-disabled .mcp-status-icon {
    background: var(--color-border);
    color: var(--color-text-tertiary);
  }

  .mcp-status-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .mcp-status-label {
    font-weight: 600;
    color: var(--color-text);
  }

  .mcp-status-endpoint,
  .mcp-status-hint {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  .mcp-status-endpoint code {
    background: var(--color-bg);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.875em;
  }

  .mcp-key-display {
    margin-bottom: var(--space-4);
  }

  .mcp-key-row {
    display: flex;
    gap: var(--space-2);
  }

  .mcp-key-row .input {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 0.8125rem;
  }

  .mcp-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  .mcp-help {
    border-top: 1px solid var(--color-border-light);
    padding-top: var(--space-4);
  }

  .mcp-help summary {
    font-weight: 500;
    cursor: pointer;
    color: var(--color-text-secondary);
    padding: var(--space-2) 0;
  }

  .mcp-help summary:hover {
    color: var(--color-text);
  }

  .mcp-help-content {
    margin-top: var(--space-3);
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  .mcp-help-content .code-block {
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-3);
    margin: var(--space-2) 0;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    line-height: 1.5;
    white-space: pre;
  }

  .mcp-help-content ul {
    margin-top: var(--space-2);
    padding-left: var(--space-4);
  }

  .mcp-help-content li {
    margin-bottom: var(--space-1);
  }

  .mcp-help-content code {
    background: var(--color-bg-sunken);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.875em;
  }

  /* Backup Section */
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    font-weight: 500;
  }

  .checkbox-label input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }

  .s3-section {
    margin-top: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
  }

  .s3-fields {
    margin-top: var(--space-3);
    padding: var(--space-4);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
  }

  .mb-3 {
    margin-bottom: var(--space-3);
  }

  .backup-actions {
    display: flex;
    gap: var(--space-2);
  }

  .backup-list {
    border-top: 1px solid var(--color-border-light);
    padding-top: var(--space-4);
  }

  .backup-list-title {
    font-size: 0.9375rem;
    font-weight: 600;
    margin-bottom: var(--space-3);
    color: var(--color-text);
  }

  .backup-items {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .backup-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3);
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    gap: var(--space-3);
  }

  .backup-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
    flex: 1;
  }

  .backup-filename {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .backup-meta {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .backup-location {
    display: inline-block;
    padding: 0.1em 0.4em;
    background: var(--color-primary-light);
    color: var(--color-primary);
    border-radius: var(--radius-sm);
    font-weight: 500;
    font-size: 0.6875rem;
    text-transform: uppercase;
    margin-left: var(--space-2);
  }

  .backup-item-actions {
    display: flex;
    gap: var(--space-1);
    flex-shrink: 0;
  }

  .modal-icon-warning {
    background: var(--color-warning-light);
    color: var(--color-warning);
  }

  .text-secondary {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }
</style>
