<script>
  import { onMount } from 'svelte';
  import { profileApi, backupsApi, emailApi } from '$lib/api';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import { toast } from '$lib/stores';
  import { countries } from '$lib/data/countries';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import SettingsApiAccessSection from '$lib/components/settings/SettingsApiAccessSection.svelte';
  import SettingsBackupSection from '$lib/components/settings/SettingsBackupSection.svelte';

  let profile = null;
  let loading = true;
  let saving = false;

  // Collapsible section states
  let openSections = {
    logo: true,
    business: true,
    address: false,
    invoiceDefaults: false,
    taxSettings: false,
    paymentMethods: false,
    smtpSettings: false,
    mcpIntegration: false,
    botApi: false,
    backup: false
  };

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
  let defaultCurrencyCode = 'USD';
  let defaultNotes = '';
  let defaultPaymentInstructions = '';

  // Tax settings
  let defaultTaxEnabled = false;
  let defaultTaxRate = '';
  let defaultTaxName = 'Tax';

  // SMTP settings
  let smtpEnabled = false;
  let smtpHost = '';
  let smtpPort = 587;
  let smtpUsername = '';
  let smtpPassword = '';
  let smtpFromEmail = '';
  let smtpFromName = '';
  let smtpUseTls = true;
  let smtpPasswordSet = false;
  let testingSmtp = false;
  let savingSmtp = false;

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
  let mcpApiKeyConfigured = false;
  let botApiKey = '';
  let botApiKeyConfigured = false;
  let appBaseUrl = '';
  let generatingMcpKey = false;
  let generatingBotKey = false;

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

  // Backup delete modal state
  let showDeleteBackupModal = false;
  let deleteBackupTarget = null;
  let deletingBackup = false;

  // MCP key delete modal state
  let showDeleteMcpModal = false;
  let deletingMcpKey = false;
  let showDeleteBotModal = false;
  let deletingBotKey = false;

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
      defaultCurrencyCode = profile.default_currency_code || 'USD';
      defaultNotes = profile.default_notes || '';
      defaultPaymentInstructions = profile.default_payment_instructions || '';

      paymentMethods = parseJsonArray(profile.payment_methods);

      if (profile.logo_path) {
        logoPreview = `/api/profile/logo/${profile.logo_path}`;
      }

      // MCP settings
      mcpApiKeyConfigured = !!profile.mcp_api_key_configured;
      botApiKeyConfigured = !!profile.bot_api_key_configured;
      mcpApiKey = '';
      botApiKey = '';
      appBaseUrl = profile.app_base_url || '';

      // Tax settings
      defaultTaxEnabled = profile.default_tax_enabled || false;
      defaultTaxRate = profile.default_tax_rate || '';
      defaultTaxName = profile.default_tax_name || 'Tax';

      // Load SMTP settings separately
      await loadSmtpSettings();
    } catch (error) {
      toast.error('Failed to load profile');
    } finally {
      loading = false;
    }
  }

  async function loadSmtpSettings() {
    try {
      const settings = await emailApi.getSmtpSettings();
      smtpEnabled = settings.smtp_enabled || false;
      smtpHost = settings.smtp_host || '';
      smtpPort = settings.smtp_port || 587;
      smtpUsername = settings.smtp_username || '';
      smtpFromEmail = settings.smtp_from_email || '';
      smtpFromName = settings.smtp_from_name || '';
      smtpUseTls = settings.smtp_use_tls !== false;
      smtpPasswordSet = settings.smtp_password_set || false;
      smtpPassword = ''; // Never show actual password
    } catch (error) {
      console.error('Failed to load SMTP settings:', error);
    }
  }

  async function saveSmtpSettings() {
    savingSmtp = true;
    try {
      const data = {
        smtp_enabled: smtpEnabled,
        smtp_host: smtpHost || undefined,
        smtp_port: Number(smtpPort) || 587,
        smtp_username: smtpUsername || undefined,
        smtp_from_email: smtpFromEmail || undefined,
        smtp_from_name: smtpFromName || undefined,
        smtp_use_tls: smtpUseTls,
      };
      // Only include password if changed
      if (smtpPassword) {
        data.smtp_password = smtpPassword;
      }
      await emailApi.updateSmtpSettings(data);
      toast.success('SMTP settings saved');
      smtpPasswordSet = !!smtpPassword || smtpPasswordSet;
      smtpPassword = '';
    } catch (error) {
      toast.error(error.message || 'Failed to save SMTP settings');
    } finally {
      savingSmtp = false;
    }
  }

  async function testSmtpConnection() {
    testingSmtp = true;
    try {
      await saveSmtpSettings();
      const result = await emailApi.testSmtp();
      toast.success(result.message || 'SMTP connection successful');
    } catch (error) {
      toast.error(error.message || 'SMTP connection failed');
    } finally {
      testingSmtp = false;
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
        default_payment_terms_days: Number(defaultPaymentTermsDays) || undefined,
        default_currency_code: defaultCurrencyCode || undefined,
        default_notes: defaultNotes || undefined,
        default_payment_instructions: defaultPaymentInstructions || undefined,
        payment_methods: stringifyJsonArray(paymentMethods),
        app_base_url: appBaseUrl || undefined,
        // Tax settings
        default_tax_enabled: defaultTaxEnabled,
        default_tax_rate: defaultTaxRate || undefined,
        default_tax_name: defaultTaxName || undefined,
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

  function handleModalKeydown(event, closeModal) {
    if (event.key === 'Escape') {
      closeModal();
    }
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
      mcpApiKeyConfigured = true;
      toast.success('MCP API key generated');
    } catch (error) {
      toast.error('Failed to generate API key');
    } finally {
      generatingMcpKey = false;
    }
  }

  function openDeleteMcpModal() {
    showDeleteMcpModal = true;
  }

  async function confirmDeleteMcpKey() {
    deletingMcpKey = true;
    try {
      await profileApi.deleteMcpKey();
      mcpApiKey = '';
      mcpApiKeyConfigured = false;
      toast.success('MCP API key deleted');
      showDeleteMcpModal = false;
    } catch (error) {
      toast.error('Failed to delete API key');
    } finally {
      deletingMcpKey = false;
    }
  }

  function cancelDeleteMcpKey() {
    showDeleteMcpModal = false;
  }

  function copyMcpKey() {
    if (!mcpApiKey) {
      toast.error('Regenerate key to copy it again');
      return;
    }
    navigator.clipboard.writeText(mcpApiKey);
    toast.success('API key copied to clipboard');
  }

  // Bot API key functions
  async function generateBotKey() {
    generatingBotKey = true;
    try {
      const result = await profileApi.generateBotKey();
      botApiKey = result.bot_api_key;
      botApiKeyConfigured = true;
      toast.success('Bot API key generated');
    } catch (error) {
      toast.error('Failed to generate bot API key');
    } finally {
      generatingBotKey = false;
    }
  }

  function openDeleteBotModal() {
    showDeleteBotModal = true;
  }

  async function confirmDeleteBotKey() {
    deletingBotKey = true;
    try {
      await profileApi.deleteBotKey();
      botApiKey = '';
      botApiKeyConfigured = false;
      toast.success('Bot API key deleted');
      showDeleteBotModal = false;
    } catch (error) {
      toast.error('Failed to delete bot API key');
    } finally {
      deletingBotKey = false;
    }
  }

  function cancelDeleteBotKey() {
    showDeleteBotModal = false;
  }

  function copyBotKey() {
    if (!botApiKey) {
      toast.error('Regenerate key to copy it again');
      return;
    }
    navigator.clipboard.writeText(botApiKey);
    toast.success('Bot API key copied to clipboard');
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
        backup_retention_days: Number(backupRetentionDays) || 30,
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

  function openDeleteBackupModal(backup) {
    deleteBackupTarget = backup;
    showDeleteBackupModal = true;
  }

  async function confirmDeleteBackup() {
    if (!deleteBackupTarget) return;
    deletingBackup = true;
    try {
      await backupsApi.delete(deleteBackupTarget.filename);
      toast.success('Backup deleted');
      showDeleteBackupModal = false;
      await loadBackups();
    } catch (error) {
      toast.error('Failed to delete backup');
    } finally {
      deletingBackup = false;
      deleteBackupTarget = null;
    }
  }

  function cancelDeleteBackup() {
    showDeleteBackupModal = false;
    deleteBackupTarget = null;
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
      <CollapsibleSection title="Logo" subtitle="Company logo for invoices" icon="image" bind:open={openSections.logo}>
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
      </CollapsibleSection>

      <!-- Business Info Form -->
      <CollapsibleSection title="Business Information" subtitle="Your company details" icon="users" bind:open={openSections.business}>
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
      </CollapsibleSection>

      <!-- Address -->
      <CollapsibleSection title="Business Address" subtitle="Your mailing address" icon="home" bind:open={openSections.address}>
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
      </CollapsibleSection>

      <!-- Invoice Defaults -->
      <CollapsibleSection title="Invoice Defaults" subtitle="Default settings for new invoices" icon="invoice" bind:open={openSections.invoiceDefaults}>
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
            <label for="default-currency" class="label">Default Currency</label>
            <select id="default-currency" class="select" bind:value={defaultCurrencyCode}>
              {#each currencies as currency}
                {#if currency.disabled}
                  <option value="" disabled>{currency.name}</option>
                {:else}
                  <option value={currency.code}>{currency.code} - {currency.name}</option>
                {/if}
              {/each}
            </select>
            <p class="form-hint">Default currency for new invoices.</p>
          </div>
        </div>

        <div class="form-row">
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
      </CollapsibleSection>

      <!-- Payment Methods -->
      <CollapsibleSection title="Payment Methods" subtitle="Configure payment options" icon="invoice" bind:open={openSections.paymentMethods}>
        <div class="section-header-actions">
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
      </CollapsibleSection>

      <!-- Tax Settings -->
      <CollapsibleSection title="Tax Settings" subtitle="Default tax configuration" icon="invoice" bind:open={openSections.taxSettings}>
        <p class="form-hint mb-4">
          Configure default tax settings for new invoices. These can be overridden on individual invoices.
        </p>

        <div class="form-group">
          <label class="toggle-container">
            <input type="checkbox" bind:checked={defaultTaxEnabled} />
            <span class="toggle-label">Enable tax by default on new invoices</span>
          </label>
        </div>

        {#if defaultTaxEnabled}
          <div class="form-row">
            <div class="form-group">
              <label for="tax-name" class="label">Tax Name</label>
              <input
                id="tax-name"
                type="text"
                class="input"
                placeholder="Tax"
                bind:value={defaultTaxName}
              />
              <p class="form-hint">e.g., "Sales Tax", "VAT", "GST"</p>
            </div>

            <div class="form-group">
              <label for="tax-rate" class="label">Tax Rate (%)</label>
              <input
                id="tax-rate"
                type="number"
                class="input"
                placeholder="0.00"
                step="0.01"
                min="0"
                max="100"
                bind:value={defaultTaxRate}
              />
              <p class="form-hint">Default tax percentage</p>
            </div>
          </div>
        {/if}
      </CollapsibleSection>

      <!-- SMTP / Email Settings -->
      <CollapsibleSection title="Email Settings (SMTP)" subtitle="Send invoices via email" icon="send" bind:open={openSections.smtpSettings}>
        <p class="form-hint mb-4">
          Configure SMTP to send invoices directly via email. Leave disabled if you prefer to download and send PDFs manually.
        </p>

        <div class="form-group">
          <label class="toggle-container">
            <input type="checkbox" bind:checked={smtpEnabled} />
            <span class="toggle-label">Enable email sending</span>
          </label>
        </div>

        {#if smtpEnabled}
          <div class="form-row">
            <div class="form-group">
              <label for="smtp-host" class="label">SMTP Host *</label>
              <input
                id="smtp-host"
                type="text"
                class="input"
                placeholder="smtp.example.com"
                bind:value={smtpHost}
              />
            </div>

            <div class="form-group">
              <label for="smtp-port" class="label">Port</label>
              <input
                id="smtp-port"
                type="number"
                class="input"
                placeholder="587"
                bind:value={smtpPort}
              />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="smtp-username" class="label">Username</label>
              <input
                id="smtp-username"
                type="text"
                class="input"
                placeholder="your@email.com"
                bind:value={smtpUsername}
              />
            </div>

            <div class="form-group">
              <label for="smtp-password" class="label">Password {smtpPasswordSet ? '(set)' : ''}</label>
              <input
                id="smtp-password"
                type="password"
                class="input"
                placeholder={smtpPasswordSet ? '••••••••' : 'Enter password'}
                bind:value={smtpPassword}
              />
              <p class="form-hint">Leave empty to keep existing password</p>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="smtp-from-email" class="label">From Email *</label>
              <input
                id="smtp-from-email"
                type="email"
                class="input"
                placeholder="invoices@example.com"
                bind:value={smtpFromEmail}
              />
            </div>

            <div class="form-group">
              <label for="smtp-from-name" class="label">From Name</label>
              <input
                id="smtp-from-name"
                type="text"
                class="input"
                placeholder="Your Business Name"
                bind:value={smtpFromName}
              />
            </div>
          </div>

          <div class="form-group">
            <label class="toggle-container">
              <input type="checkbox" bind:checked={smtpUseTls} />
              <span class="toggle-label">Use TLS encryption</span>
            </label>
            <p class="form-hint">Recommended for security. Use port 587 for STARTTLS or 465 for SSL.</p>
          </div>

          <div class="form-actions">
            <button
              class="btn btn-secondary"
              on:click={testSmtpConnection}
              disabled={testingSmtp || !smtpHost || !smtpFromEmail}
            >
              {#if testingSmtp}
                <span class="spinner-sm"></span>
                Testing...
              {:else}
                <Icon name="send" size="sm" />
                Test Connection
              {/if}
            </button>

            <button
              class="btn btn-primary"
              on:click={saveSmtpSettings}
              disabled={savingSmtp}
            >
              {#if savingSmtp}
                <span class="spinner-sm"></span>
                Saving...
              {:else}
                Save SMTP Settings
              {/if}
            </button>
          </div>

          <div class="template-link">
            <a href="/settings/email-templates" class="btn btn-ghost">
              <Icon name="pencil" size="sm" />
              Configure Email Templates
            </a>
            <p class="form-hint">Customize the default subject and body for invoice emails</p>
          </div>
        {/if}
      </CollapsibleSection>

      <SettingsApiAccessSection
        bind:mcpOpen={openSections.mcpIntegration}
        bind:botOpen={openSections.botApi}
        bind:appBaseUrl
        {mcpEndpointUrl}
        {mcpApiKeyConfigured}
        {mcpApiKey}
        {generatingMcpKey}
        {copyMcpKey}
        {openDeleteMcpModal}
        {generateMcpKey}
        {botApiKeyConfigured}
        {botApiKey}
        {generatingBotKey}
        {copyBotKey}
        {openDeleteBotModal}
        {generateBotKey}
      />

      <SettingsBackupSection
        bind:open={openSections.backup}
        {creatingBackup}
        {createBackup}
        bind:backupEnabled
        bind:backupRetentionDays
        bind:backupS3Enabled
        bind:backupS3EndpointUrl
        bind:backupS3AccessKeyId
        bind:backupS3SecretAccessKey
        bind:backupS3Bucket
        bind:backupS3Region
        bind:backupS3Prefix
        {testingS3}
        {testS3Connection}
        {saveBackupSettings}
        {loadingBackups}
        {backups}
        {restoringBackup}
        {openRestoreModal}
        {openDeleteBackupModal}
        {formatBytes}
        {formatDate}
        downloadBackupHref={backupsApi.download}
      />

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
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={(event) => handleModalKeydown(event, closeDeleteLogoModal)}>
    <button type="button" class="modal-backdrop" aria-label="Close delete logo dialog" on:click={closeDeleteLogoModal}></button>
    <div class="modal modal-sm" role="dialog" aria-modal="true" tabindex="-1">
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
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={(event) => handleModalKeydown(event, closeRestoreModal)}>
    <button type="button" class="modal-backdrop" aria-label="Close restore backup dialog" on:click={closeRestoreModal}></button>
    <div class="modal modal-sm" role="dialog" aria-modal="true" tabindex="-1">
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
  <div class="modal-overlay" role="presentation" tabindex="-1" on:keydown={(event) => handleModalKeydown(event, closePaymentMethodModal)}>
    <button type="button" class="modal-backdrop" aria-label="Close payment method dialog" on:click={closePaymentMethodModal}></button>
    <div class="modal" role="dialog" aria-modal="true" tabindex="-1">
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

<!-- Delete MCP Key Modal -->
<ConfirmModal
  show={showDeleteMcpModal}
  title="Disable Remote Access"
  message="This will delete your MCP API key and disable remote Claude Desktop connections. You'll need to generate a new key to reconnect."
  confirmText="Disable"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deletingMcpKey}
  onConfirm={confirmDeleteMcpKey}
  onCancel={cancelDeleteMcpKey}
/>

<!-- Delete Bot API Key Modal -->
<ConfirmModal
  show={showDeleteBotModal}
  title="Disable Bot API Access"
  message="This will delete your bot API key and disable bearer-token automation for /api endpoints."
  confirmText="Disable"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deletingBotKey}
  onConfirm={confirmDeleteBotKey}
  onCancel={cancelDeleteBotKey}
/>

<!-- Delete Backup Modal -->
<ConfirmModal
  show={showDeleteBackupModal}
  title="Delete Backup"
  message="Delete backup {deleteBackupTarget?.filename}? This action cannot be undone."
  confirmText="Delete"
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deletingBackup}
  onConfirm={confirmDeleteBackup}
  onCancel={cancelDeleteBackup}
/>

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

  .section-header-actions {
    display: flex;
    justify-content: flex-end;
    margin-bottom: var(--space-4);
  }

  /* Delete Modal */
  .modal-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }

  .modal-sm {
    position: relative;
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

  .modal-icon-warning {
    background: var(--color-warning-light);
    color: var(--color-warning);
  }

  .text-secondary {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  /* Toggle container for checkbox toggles */
  .toggle-container {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    cursor: pointer;
    user-select: none;
  }

  .toggle-container input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: var(--color-primary);
    cursor: pointer;
  }

  .toggle-label {
    font-size: 0.9375rem;
    color: var(--color-text);
  }

  /* Spinner for buttons */
  .spinner-sm {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
    display: inline-block;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Email Template Link */
  .template-link {
    margin-top: var(--space-6);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-border-light);
  }

  .template-link .form-hint {
    margin-top: var(--space-2);
  }
</style>
