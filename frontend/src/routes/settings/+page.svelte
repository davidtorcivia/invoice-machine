<script>
  import { onMount } from 'svelte';
  import { beforeNavigate } from '$app/navigation';
  import { profileApi, backupsApi, emailApi } from '$lib/api';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import {
    buildBackupPayload,
    buildProfilePayload,
    buildSmtpPayload,
    createApiAccessState,
    createBackupForm,
    createPaymentMethodDraft,
    createProfileForm,
    createSmtpForm,
    DEFAULT_SETTINGS_SECTIONS,
    formatBackupBytes,
    formatBackupDate,
    mapBackupSettingsToForm,
    mapProfileToApiAccess,
    mapProfileToProfileForm,
    mapSmtpSettingsToForm
  } from '$lib/settings/forms';
  import { toast } from '$lib/stores';
  import { countries } from '$lib/data/countries';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
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
  let openSections = { ...DEFAULT_SETTINGS_SECTIONS };
  let profileForm = createProfileForm();
  let smtpForm = createSmtpForm();
  let backupForm = createBackupForm();
  let apiAccess = createApiAccessState();

  let paymentMethods = [];
  let editingMethod = null;
  let paymentMethodDraft = createPaymentMethodDraft();
  let showPaymentMethodModal = false;

  let logoPreview = null;
  let logoUploading = false;
  let showDeleteLogoModal = false;
  let deletingLogo = false;

  let loadingBackups = false;
  let backups = [];
  let creatingBackup = false;
  let restoringBackup = null;
  let testingS3 = false;
  let showRestoreModal = false;
  let restoreTarget = null;
  let showDeleteBackupModal = false;
  let deleteBackupTarget = null;
  let deletingBackup = false;

  let testingSmtp = false;
  let savingSmtp = false;
  let showDeleteMcpModal = false;
  let deletingMcpKey = false;
  let showDeleteBotModal = false;
  let deletingBotKey = false;
  let generatingMcpKey = false;
  let generatingBotKey = false;

  $: mcpEndpointUrl = apiAccess.appBaseUrl || (typeof window !== 'undefined' ? window.location.origin : '');

  // Unsaved-changes guard. The page has three independent deferred-save forms
  // (business profile incl. payment methods + app URL, SMTP, backup), so each is
  // tracked separately and re-baselined after its own save — that way saving one
  // never suppresses an unsaved warning for another, and a single prompt covers
  // any dirty form. Immediate actions (logo, API keys) are not tracked.
  let allowLeaveSettings = false;
  let profileSnapshot = '';
  let smtpSnapshot = '';
  let backupSnapshot = '';

  const profileState = () =>
    JSON.stringify({ profileForm, paymentMethods, appBaseUrl: apiAccess.appBaseUrl });
  const smtpState = () => JSON.stringify(smtpForm);
  const backupState = () => JSON.stringify(backupForm);

  $: settingsDirty =
    (profileSnapshot !== '' && profileState() !== profileSnapshot) ||
    (smtpSnapshot !== '' && smtpState() !== smtpSnapshot) ||
    (backupSnapshot !== '' && backupState() !== backupSnapshot);

  beforeNavigate((nav) => {
    if (settingsDirty && !allowLeaveSettings && !saving && !savingSmtp) {
      if (!confirm('You have unsaved changes. Leave without saving?')) {
        nav.cancel();
      }
    }
  });

  onMount(async () => {
    await loadProfile();
    await loadBackupSettings();
    await loadBackups();
  });

  async function loadProfile() {
    loading = true;
    try {
      profile = await profileApi.get();
      profileForm = mapProfileToProfileForm(profile);
      apiAccess = mapProfileToApiAccess(profile);
      paymentMethods = parseJsonArray(profile.payment_methods);
      logoPreview = profile.logo_path ? `/api/profile/logo/${profile.logo_path}` : null;
      await loadSmtpSettings();
      profileSnapshot = profileState();
      smtpSnapshot = smtpState();
    } catch (error) {
      toast.error('Failed to load profile');
    } finally {
      loading = false;
    }
  }

  async function loadSmtpSettings() {
    try {
      smtpForm = mapSmtpSettingsToForm(await emailApi.getSmtpSettings());
    } catch (error) {
      console.error('Failed to load SMTP settings:', error);
    }
  }

  async function saveSmtpSettings() {
    savingSmtp = true;
    try {
      await emailApi.updateSmtpSettings(buildSmtpPayload(smtpForm));
      toast.success('SMTP settings saved');
      smtpForm = { ...smtpForm, passwordSet: !!smtpForm.password || smtpForm.passwordSet, password: '' };
      smtpSnapshot = smtpState();
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
    if (!profileForm.name.trim()) {
      toast.error('Please enter your name');
      return;
    }

    saving = true;
    try {
      await profileApi.update(buildProfilePayload(profileForm, stringifyJsonArray(paymentMethods), apiAccess.appBaseUrl));
      toast.success('Settings saved successfully');
      profileSnapshot = profileState();
    } catch (error) {
      toast.error('Failed to save settings');
    } finally {
      saving = false;
    }
  }

  async function handleLogoSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be less than 5MB');
      return;
    }

    logoUploading = true;

    try {
      const result = await profileApi.uploadLogo(file);
      logoPreview = `/api/profile/logo/${result.logo_path}`;
      toast.success('Logo uploaded successfully');
    } catch (error) {
      toast.error('Failed to upload logo');
    } finally {
      logoUploading = false;
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

  function openAddMethodModal() {
    editingMethod = null;
    paymentMethodDraft = createPaymentMethodDraft();
    showPaymentMethodModal = true;
  }

  function openEditMethodModal(method) {
    editingMethod = method;
    paymentMethodDraft = { name: method.name, instructions: method.instructions };
    showPaymentMethodModal = true;
  }

  function closePaymentMethodModal() {
    showPaymentMethodModal = false;
    editingMethod = null;
    paymentMethodDraft = createPaymentMethodDraft();
  }

  function savePaymentMethod() {
    if (!paymentMethodDraft.name.trim()) {
      toast.error('Please enter a method name');
      return;
    }

    if (editingMethod) {
      paymentMethods = paymentMethods.map((method) =>
        method.id === editingMethod.id
          ? { ...method, name: paymentMethodDraft.name.trim(), instructions: paymentMethodDraft.instructions.trim() }
          : method
      );
    } else {
      paymentMethods = [
        ...paymentMethods,
        { id: Date.now().toString(), name: paymentMethodDraft.name.trim(), instructions: paymentMethodDraft.instructions.trim() }
      ];
    }

    closePaymentMethodModal();
  }

  function deletePaymentMethod(id) {
    paymentMethods = paymentMethods.filter((method) => method.id !== id);
  }

  async function generateMcpKey() {
    generatingMcpKey = true;
    try {
      const result = await profileApi.generateMcpKey();
      apiAccess = { ...apiAccess, mcpApiKey: result.mcp_api_key, mcpApiKeyConfigured: true };
      toast.success('MCP API key generated');
    } catch (error) {
      toast.error('Failed to generate API key');
    } finally {
      generatingMcpKey = false;
    }
  }

  async function generateBotKey() {
    generatingBotKey = true;
    try {
      const result = await profileApi.generateBotKey();
      apiAccess = { ...apiAccess, botApiKey: result.bot_api_key, botApiKeyConfigured: true };
      toast.success('Bot API key generated');
    } catch (error) {
      toast.error('Failed to generate bot API key');
    } finally {
      generatingBotKey = false;
    }
  }

  function openDeleteMcpModal() {
    showDeleteMcpModal = true;
  }

  function openDeleteBotModal() {
    showDeleteBotModal = true;
  }

  async function confirmDeleteMcpKey() {
    deletingMcpKey = true;
    try {
      await profileApi.deleteMcpKey();
      apiAccess = { ...apiAccess, mcpApiKey: '', mcpApiKeyConfigured: false };
      toast.success('MCP API key deleted');
      showDeleteMcpModal = false;
    } catch (error) {
      toast.error('Failed to delete API key');
    } finally {
      deletingMcpKey = false;
    }
  }

  async function confirmDeleteBotKey() {
    deletingBotKey = true;
    try {
      await profileApi.deleteBotKey();
      apiAccess = { ...apiAccess, botApiKey: '', botApiKeyConfigured: false };
      toast.success('Bot API key deleted');
      showDeleteBotModal = false;
    } catch (error) {
      toast.error('Failed to delete bot API key');
    } finally {
      deletingBotKey = false;
    }
  }

  async function copyToClipboard(value, successMsg) {
    if (!navigator.clipboard?.writeText) {
      toast.error('Clipboard is unavailable (requires HTTPS). Copy the key manually.');
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      toast.success(successMsg);
    } catch {
      toast.error('Could not copy to clipboard. Copy the key manually.');
    }
  }

  async function copyMcpKey() {
    if (!apiAccess.mcpApiKey) {
      toast.error('Regenerate key to copy it again');
      return;
    }
    await copyToClipboard(apiAccess.mcpApiKey, 'API key copied to clipboard');
  }

  async function copyBotKey() {
    if (!apiAccess.botApiKey) {
      toast.error('Regenerate key to copy it again');
      return;
    }
    await copyToClipboard(apiAccess.botApiKey, 'Bot API key copied to clipboard');
  }

  async function loadBackupSettings() {
    try {
      backupForm = mapBackupSettingsToForm(await backupsApi.getSettings());
    } catch (error) {
      // Use defaults.
    } finally {
      backupSnapshot = backupState();
    }
  }

  async function loadBackups() {
    loadingBackups = true;
    try {
      backups = await backupsApi.list(backupForm.s3Enabled);
    } catch (error) {
      backups = [];
    } finally {
      loadingBackups = false;
    }
  }

  async function saveBackupSettings() {
    try {
      await backupsApi.updateSettings(buildBackupPayload(backupForm));
      toast.success('Backup settings saved');
      backupSnapshot = backupState();
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
      const result = await backupsApi.restore(restoreTarget.filename, restoreTarget.location === 's3');
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

  async function testS3Connection() {
    testingS3 = true;
    try {
      await saveBackupSettings();
      const result = await backupsApi.testS3();
      toast.success(result.message);
    } catch (error) {
      toast.error(error.message || 'S3 connection failed');
    } finally {
      testingS3 = false;
    }
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
        {handleLogoSelect}
        {openDeleteLogoModal}
      />

      <SettingsBusinessInfoSection
        bind:open={openSections.business}
        bind:name={profileForm.name}
        bind:businessName={profileForm.businessName}
        bind:email={profileForm.email}
        bind:phone={profileForm.phone}
        bind:ein={profileForm.ein}
      />

      <SettingsAddressSection
        bind:open={openSections.address}
        bind:addressLine1={profileForm.addressLine1}
        bind:addressLine2={profileForm.addressLine2}
        bind:city={profileForm.city}
        bind:state={profileForm.state}
        bind:postalCode={profileForm.postalCode}
        bind:country={profileForm.country}
        {countries}
      />

      <SettingsInvoiceDefaultsSection
        bind:open={openSections.invoiceDefaults}
        bind:defaultPaymentTermsDays={profileForm.defaultPaymentTermsDays}
        bind:defaultCurrencyCode={profileForm.defaultCurrencyCode}
        {currencies}
        bind:accentColor={profileForm.accentColor}
        bind:defaultNotes={profileForm.defaultNotes}
        bind:defaultPaymentInstructions={profileForm.defaultPaymentInstructions}
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
        bind:defaultTaxEnabled={profileForm.defaultTaxEnabled}
        bind:defaultTaxName={profileForm.defaultTaxName}
        bind:defaultTaxRate={profileForm.defaultTaxRate}
      />

      <SettingsSmtpSection
        bind:open={openSections.smtpSettings}
        bind:smtpEnabled={smtpForm.enabled}
        bind:smtpHost={smtpForm.host}
        bind:smtpPort={smtpForm.port}
        bind:smtpUsername={smtpForm.username}
        bind:smtpPassword={smtpForm.password}
        bind:smtpFromEmail={smtpForm.fromEmail}
        bind:smtpFromName={smtpForm.fromName}
        bind:smtpUseTls={smtpForm.useTls}
        smtpPasswordSet={smtpForm.passwordSet}
        {testingSmtp}
        {savingSmtp}
        {testSmtpConnection}
        {saveSmtpSettings}
      />

      <SettingsApiAccessSection
        bind:mcpOpen={openSections.mcpIntegration}
        bind:botOpen={openSections.botApi}
        bind:appBaseUrl={apiAccess.appBaseUrl}
        {mcpEndpointUrl}
        mcpApiKeyConfigured={apiAccess.mcpApiKeyConfigured}
        mcpApiKey={apiAccess.mcpApiKey}
        {generatingMcpKey}
        {copyMcpKey}
        {openDeleteMcpModal}
        {generateMcpKey}
        botApiKeyConfigured={apiAccess.botApiKeyConfigured}
        botApiKey={apiAccess.botApiKey}
        {generatingBotKey}
        {copyBotKey}
        {openDeleteBotModal}
        {generateBotKey}
      />

      <SettingsBackupSection
        bind:open={openSections.backup}
        {creatingBackup}
        {createBackup}
        bind:backupEnabled={backupForm.enabled}
        bind:backupRetentionDays={backupForm.retentionDays}
        bind:backupS3Enabled={backupForm.s3Enabled}
        bind:backupS3EndpointUrl={backupForm.s3EndpointUrl}
        bind:backupS3AccessKeyId={backupForm.s3AccessKeyId}
        bind:backupS3SecretAccessKey={backupForm.s3SecretAccessKey}
        bind:backupS3Bucket={backupForm.s3Bucket}
        bind:backupS3Region={backupForm.s3Region}
        bind:backupS3Prefix={backupForm.s3Prefix}
        {testingS3}
        {testS3Connection}
        {saveBackupSettings}
        {loadingBackups}
        {backups}
        {restoringBackup}
        {openRestoreModal}
        {openDeleteBackupModal}
        formatBytes={formatBackupBytes}
        formatDate={formatBackupDate}
        downloadBackupHref={backupsApi.download}
      />

      <div class="form-actions">
        <p class="form-hint save-scope-hint">
          Saves your business profile, branding, defaults and payment methods.
          The Email (SMTP) and Backup sections each have their own Save button.
        </p>
        <button type="button" class="btn btn-primary" on:click={saveProfile} disabled={saving}>
          <Icon name="check" size="sm" />
          {saving ? 'Saving...' : 'Save Business Profile'}
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
  bind:newMethodName={paymentMethodDraft.name}
  bind:newMethodInstructions={paymentMethodDraft.instructions}
  {closePaymentMethodModal}
  {savePaymentMethod}
/>

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
  onCancel={() => showDeleteMcpModal = false}
/>

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
  onCancel={() => showDeleteBotModal = false}
/>

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
  onCancel={() => {
    showDeleteBackupModal = false;
    deleteBackupTarget = null;
  }}
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

  @media (max-width: 480px) {
    .page-content {
      padding: var(--space-3);
    }

    .form-actions .btn {
      width: 100%;
    }
  }
</style>
