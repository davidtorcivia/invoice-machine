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
  import SettingsAddressSection from '$lib/components/settings/SettingsAddressSection.svelte';
  import SettingsBackupSection from '$lib/components/settings/SettingsBackupSection.svelte';
  import SettingsBusinessInfoSection from '$lib/components/settings/SettingsBusinessInfoSection.svelte';
  import SettingsInvoiceDefaultsSection from '$lib/components/settings/SettingsInvoiceDefaultsSection.svelte';
  import SettingsLogoSection from '$lib/components/settings/SettingsLogoSection.svelte';
  import SettingsPaymentMethodModal from '$lib/components/settings/SettingsPaymentMethodModal.svelte';
  import SettingsPaymentMethodsSection from '$lib/components/settings/SettingsPaymentMethodsSection.svelte';
  import SettingsSmtpSection from '$lib/components/settings/SettingsSmtpSection.svelte';
  import SettingsTaxSection from '$lib/components/settings/SettingsTaxSection.svelte';

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
      <SettingsLogoSection
        bind:open={openSections.logo}
        {logoPreview}
        {logoUploading}
        {uploadProgress}
        {handleLogoSelect}
        {openDeleteLogoModal}
      />

      <SettingsBusinessInfoSection
        bind:open={openSections.business}
        bind:name
        bind:businessName
        bind:email
        bind:phone
        bind:ein
      />

      <SettingsAddressSection
        bind:open={openSections.address}
        bind:addressLine1
        bind:addressLine2
        bind:city
        bind:state
        bind:postalCode
        bind:country
        {countries}
      />

      <SettingsInvoiceDefaultsSection
        bind:open={openSections.invoiceDefaults}
        bind:defaultPaymentTermsDays
        bind:defaultCurrencyCode
        {currencies}
        bind:accentColor
        bind:defaultNotes
        bind:defaultPaymentInstructions
      />

      <SettingsPaymentMethodsSection
        bind:open={openSections.paymentMethods}
        {paymentMethods}
        {openAddMethodModal}
        {openEditMethodModal}
        {deletePaymentMethod}
      />

      <SettingsTaxSection
        bind:open={openSections.taxSettings}
        bind:defaultTaxEnabled
        bind:defaultTaxName
        bind:defaultTaxRate
      />

      <SettingsSmtpSection
        bind:open={openSections.smtpSettings}
        bind:smtpEnabled
        bind:smtpHost
        bind:smtpPort
        bind:smtpUsername
        bind:smtpPassword
        bind:smtpFromEmail
        bind:smtpFromName
        bind:smtpUseTls
        {smtpPasswordSet}
        {testingSmtp}
        {savingSmtp}
        {testSmtpConnection}
        {saveSmtpSettings}
      />

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

<ConfirmModal
  show={showDeleteLogoModal}
  title="Delete Logo"
  message="This will remove your logo from all invoices. This action cannot be undone."
  confirmText={deletingLogo ? 'Deleting...' : 'Delete Logo'}
  cancelText="Cancel"
  variant="danger"
  icon="trash"
  loading={deletingLogo}
  onConfirm={deleteLogo}
  onCancel={closeDeleteLogoModal}
/>

<ConfirmModal
  show={showRestoreModal && !!restoreTarget}
  title="Restore Backup"
  message={restoreTarget
    ? `This will overwrite your current database with ${restoreTarget.filename}. A pre-restore backup will be created automatically. The application will need to be restarted after restore.`
    : 'Restore this backup?'}
  confirmText={restoringBackup ? 'Restoring...' : 'Restore Backup'}
  cancelText="Cancel"
  variant="warning"
  icon="refresh"
  loading={!!restoringBackup}
  onConfirm={restoreBackup}
  onCancel={closeRestoreModal}
/>

<SettingsPaymentMethodModal
  show={showPaymentMethodModal}
  {editingMethod}
  bind:newMethodName
  bind:newMethodInstructions
  {closePaymentMethodModal}
  {savePaymentMethod}
/>

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

  .form-actions {
    display: flex;
    justify-content: flex-end;
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
  }

  /* Small screens */
  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .form-actions .btn {
      width: 100%;
    }
  }
</style>
