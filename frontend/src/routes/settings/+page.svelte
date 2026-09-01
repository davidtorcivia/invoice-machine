<script>
  import { onMount } from 'svelte';
  import { beforeNavigate } from '$app/navigation';
  import {
    profileApi,
    backupsApi,
    emailApi,
    paymentSettingsApi,
    remindersApi,
    fxRatesApi
  } from '$lib/api';
  import { parseJsonArray, stringifyJsonArray } from '$lib/json';
  import {
    buildBackupPayload,
    buildProfilePayload,
    buildSmtpPayload,
    createApiAccessState,
    createBackupForm,
    createProfileForm,
    createSmtpForm,
    DEFAULT_SETTINGS_SECTIONS,
    mapBackupSettingsToForm,
    mapProfileToApiAccess,
    mapProfileToProfileForm,
    mapSmtpSettingsToForm
  } from '$lib/settings/forms';
  import { auth, toast } from '$lib/stores';
  import { countries } from '$lib/data/countries';
  import { currencies } from '$lib/data/currencies';
  import Header from '$lib/components/Header.svelte';
  import SettingsApiAccessSection from '$lib/components/settings/SettingsApiAccessSection.svelte';
  import SettingsAccountSection from '$lib/components/settings/SettingsAccountSection.svelte';
  import SettingsAddressSection from '$lib/components/settings/SettingsAddressSection.svelte';
  import SettingsBackupSection from '$lib/components/settings/SettingsBackupSection.svelte';
  import SettingsBusinessInfoSection from '$lib/components/settings/SettingsBusinessInfoSection.svelte';
  import SettingsInvoiceDefaultsSection from '$lib/components/settings/SettingsInvoiceDefaultsSection.svelte';
  import SettingsLogoSection from '$lib/components/settings/SettingsLogoSection.svelte';
  import SettingsPaymentMethodsSection from '$lib/components/settings/SettingsPaymentMethodsSection.svelte';
  import SettingsSaveBar from '$lib/components/settings/SettingsSaveBar.svelte';
  import SettingsSmtpSection from '$lib/components/settings/SettingsSmtpSection.svelte';
  import SettingsTaxSection from '$lib/components/settings/SettingsTaxSection.svelte';
  import SettingsPaymentsSection from '$lib/components/settings/SettingsPaymentsSection.svelte';
  import SettingsRemindersSection from '$lib/components/settings/SettingsRemindersSection.svelte';
  import SettingsFxRatesSection from '$lib/components/settings/SettingsFxRatesSection.svelte';

  let profile = null;
  let loading = $state(true);
  let openSections = $state({ ...DEFAULT_SETTINGS_SECTIONS });
  let profileForm = $state(createProfileForm());
  let smtpForm = $state(createSmtpForm());
  let backupForm = $state(createBackupForm());
  let apiAccess = $state(createApiAccessState());

  let paymentMethods = $state([]);
  let logoPreview = $state(/** @type {any} */ (null));
  let backupSection = $state(/** @type {any} */ (null));

  let testingS3 = $state(false);
  let testingSmtp = $state(false);
  let changingPassword = $state(false);

  let mcpEndpointUrl = $derived(apiAccess.appBaseUrl || (typeof window !== 'undefined' ? window.location.origin : ''));

  // Each deferred-save form is tracked against its own post-load snapshot and
  // re-baselined after its own save. The dirty expressions must reference the
  // form variables directly — Svelte does not trace dependencies through
  // helper-function bodies.
  let savingAll = $state(false);
  let profileSnapshot = $state('');
  let smtpSnapshot = $state('');
  let backupSnapshot = $state('');

  let paymentsForm = $state({
    payments_enabled: false,
    stripe_secret_key_set: false,
    stripe_webhook_secret_set: false,
    webhook_url: null
  });
  // Write-only: blank means "keep the stored credential".
  let stripeSecretKey = $state('');
  let stripeWebhookSecret = $state('');
  let testingPayments = $state(false);
  let paymentsSnapshot = $state('');

  let remindersForm = $state({
    reminders_enabled: false,
    reminder_offsets: [-3, 1, 7, 14],
    reminder_subject_template: '',
    reminder_body_template: '',
    business_timezone: 'UTC',
    reminder_send_hour: 9,
    local_time: null,
    smtp_enabled: false,
    default_subject: '',
    default_body: ''
  });
  let runningReminders = $state(false);
  let remindersSnapshot = $state('');

  let fxRates = $state({ base_currency_code: 'USD', rates: {} });
  let fxSnapshot = $state('');

  const profileState = () =>
    JSON.stringify({ profileForm, paymentMethods, appBaseUrl: apiAccess.appBaseUrl });
  const smtpState = () => JSON.stringify(smtpForm);
  const backupState = () => JSON.stringify(backupForm);

  let profileDirty =
    $derived(profileSnapshot !== '' &&
    JSON.stringify({ profileForm, paymentMethods, appBaseUrl: apiAccess.appBaseUrl }) !== profileSnapshot);
  let smtpDirty = $derived(smtpSnapshot !== '' && JSON.stringify(smtpForm) !== smtpSnapshot);
  let backupDirty = $derived(backupSnapshot !== '' && JSON.stringify(backupForm) !== backupSnapshot);
  let paymentsDirty =
    $derived(paymentsSnapshot !== '' &&
    (JSON.stringify(paymentsForm) !== paymentsSnapshot ||
      !!stripeSecretKey ||
      !!stripeWebhookSecret));
  let remindersDirty =
    $derived(remindersSnapshot !== '' && JSON.stringify(remindersForm) !== remindersSnapshot);
  let fxDirty = $derived(fxSnapshot !== '' && JSON.stringify(fxRates) !== fxSnapshot);
  let settingsDirty =
    $derived(profileDirty || smtpDirty || backupDirty || paymentsDirty || remindersDirty || fxDirty);
  let dirtySectionLabels = $derived([
    profileDirty && 'Business profile',
    smtpDirty && 'Email (SMTP)',
    backupDirty && 'Backup',
    paymentsDirty && 'Online payments',
    remindersDirty && 'Payment reminders',
    fxDirty && 'Exchange rates'
  ].filter(Boolean));

  beforeNavigate((nav) => {
    if (settingsDirty && !savingAll) {
      if (!confirm('You have unsaved changes. Leave without saving?')) {
        nav.cancel();
      }
    }
  });

  onMount(async () => {
    await loadProfile();
    await loadBackupSettings();
    // Listing backups depends on the s3Enabled flag that loadBackupSettings sets.
    await backupSection?.reloadBackups();
    await loadPaymentSettings();
    await loadReminderSettings();
    await loadFxRates();
  });

  async function loadPaymentSettings() {
    try {
      paymentsForm = await paymentSettingsApi.get();
      stripeSecretKey = '';
      stripeWebhookSecret = '';
      paymentsSnapshot = JSON.stringify(paymentsForm);
    } catch (error) {
      console.error('Failed to load payment settings:', error);
    }
  }

  async function loadReminderSettings() {
    try {
      const data = await remindersApi.get();
      remindersForm = {
        ...data,
        reminder_subject_template: data.reminder_subject_template || '',
        reminder_body_template: data.reminder_body_template || ''
      };
      remindersSnapshot = JSON.stringify(remindersForm);
    } catch (error) {
      console.error('Failed to load reminder settings:', error);
    }
  }

  async function loadFxRates() {
    try {
      fxRates = await fxRatesApi.get();
      fxSnapshot = JSON.stringify(fxRates);
    } catch (error) {
      console.error('Failed to load exchange rates:', error);
    }
  }

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

  // persist* helpers save one form and re-baseline its snapshot; they throw on
  // failure so callers (saveAll, the test-connection flows) control the toasts.
  async function persistProfile() {
    await profileApi.update(buildProfilePayload(profileForm, stringifyJsonArray(paymentMethods), apiAccess.appBaseUrl));
    profileSnapshot = profileState();
  }

  async function persistSmtp() {
    await emailApi.updateSmtpSettings(buildSmtpPayload(smtpForm));
    smtpForm = { ...smtpForm, passwordSet: !!smtpForm.password || smtpForm.passwordSet, password: '' };
    smtpSnapshot = smtpState();
  }

  async function persistBackup() {
    await backupsApi.updateSettings(buildBackupPayload(backupForm));
    backupSnapshot = backupState();
  }

  async function persistPayments() {
    const payload = { payments_enabled: paymentsForm.payments_enabled };
    // Only send credentials the user actually typed, so a blank field keeps the
    // stored value rather than wiping it.
    if (stripeSecretKey) payload.stripe_secret_key = stripeSecretKey;
    if (stripeWebhookSecret) payload.stripe_webhook_secret = stripeWebhookSecret;

    paymentsForm = await paymentSettingsApi.update(payload);
    stripeSecretKey = '';
    stripeWebhookSecret = '';
    paymentsSnapshot = JSON.stringify(paymentsForm);
  }

  async function persistReminders() {
    const data = await remindersApi.update({
      reminders_enabled: remindersForm.reminders_enabled,
      reminder_offsets: remindersForm.reminder_offsets,
      reminder_subject_template: remindersForm.reminder_subject_template || '',
      reminder_body_template: remindersForm.reminder_body_template || '',
      business_timezone: remindersForm.business_timezone,
      reminder_send_hour: remindersForm.reminder_send_hour
    });
    remindersForm = {
      ...data,
      reminder_subject_template: data.reminder_subject_template || '',
      reminder_body_template: data.reminder_body_template || ''
    };
    remindersSnapshot = JSON.stringify(remindersForm);
  }

  async function persistFxRates() {
    fxRates = await fxRatesApi.update(fxRates.rates);
    fxSnapshot = JSON.stringify(fxRates);
  }

  async function saveAll() {
    if (profileDirty && !profileForm.name.trim()) {
      toast.error('Please enter your name');
      return;
    }

    savingAll = true;
    try {
      if (profileDirty) await persistProfile();
      if (smtpDirty) await persistSmtp();
      if (backupDirty) await persistBackup();
      if (paymentsDirty) await persistPayments();
      if (remindersDirty) await persistReminders();
      if (fxDirty) await persistFxRates();
      toast.success('Settings saved');
    } catch (error) {
      toast.error(error.message || 'Failed to save settings');
    } finally {
      savingAll = false;
    }
  }

  async function testPaymentCredentials() {
    testingPayments = true;
    try {
      if (paymentsDirty) await persistPayments();
      const result = await paymentSettingsApi.test();
      toast.success(result.warning || result.message || 'Stripe credentials verified');
    } catch (error) {
      toast.error(error.message || 'Could not verify Stripe credentials');
    } finally {
      testingPayments = false;
    }
  }

  async function runRemindersNow() {
    runningReminders = true;
    try {
      if (remindersDirty) await persistReminders();
      const result = await remindersApi.runNow();
      if (result.attempted === 0) {
        toast.info('No reminders are due right now');
      } else {
        toast.success(`Sent ${result.sent} of ${result.attempted} reminders`);
      }
    } catch (error) {
      toast.error(error.message || 'Failed to send reminders');
    } finally {
      runningReminders = false;
    }
  }

  function discardChanges() {
    if (profileSnapshot) {
      const snap = JSON.parse(profileSnapshot);
      profileForm = snap.profileForm;
      paymentMethods = snap.paymentMethods;
      apiAccess = { ...apiAccess, appBaseUrl: snap.appBaseUrl };
    }
    if (smtpSnapshot) smtpForm = JSON.parse(smtpSnapshot);
    if (backupSnapshot) backupForm = JSON.parse(backupSnapshot);
    if (paymentsSnapshot) paymentsForm = JSON.parse(paymentsSnapshot);
    if (remindersSnapshot) remindersForm = JSON.parse(remindersSnapshot);
    if (fxSnapshot) fxRates = JSON.parse(fxSnapshot);
    stripeSecretKey = '';
    stripeWebhookSecret = '';
  }

  async function testSmtpConnection() {
    testingSmtp = true;
    try {
      if (smtpDirty) await persistSmtp();
      const result = await emailApi.testSmtp();
      toast.success(result.message || 'SMTP connection successful');
    } catch (error) {
      toast.error(error.message || 'SMTP connection failed');
    } finally {
      testingSmtp = false;
    }
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

  async function changePassword(currentPassword, newPassword) {
    changingPassword = true;
    try {
      await auth.changePassword(currentPassword, newPassword);
      toast.success('Password updated. Other sessions have been signed out.');
    } catch (error) {
      toast.error(error.message || 'Failed to update password');
      throw error;
    } finally {
      changingPassword = false;
    }
  }

  async function testS3Connection() {
    testingS3 = true;
    try {
      if (backupDirty) await persistBackup();
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
      <SettingsLogoSection bind:open={openSections.logo} bind:logoPreview />

      <SettingsAccountSection
        bind:open={openSections.account}
        username={$auth.username}
        changing={changingPassword}
        onchange={changePassword}
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
        bind:paymentMethods
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
        {testSmtpConnection}
      />

      <SettingsRemindersSection
        bind:settings={remindersForm}
        running={runningReminders}
        onrunnow={runRemindersNow}
      />

      <SettingsPaymentsSection
        bind:settings={paymentsForm}
        bind:secretKey={stripeSecretKey}
        bind:webhookSecret={stripeWebhookSecret}
        testing={testingPayments}
        ontest={testPaymentCredentials}
        oncopied={() => toast.success('Webhook URL copied')}
        oncopyfailed={() => toast.error('Could not copy the URL')}
      />

      <SettingsFxRatesSection bind:fxRates />

      <SettingsApiAccessSection
        bind:mcpOpen={openSections.mcpIntegration}
        bind:botOpen={openSections.botApi}
        bind:appBaseUrl={apiAccess.appBaseUrl}
        {mcpEndpointUrl}
      />

      <SettingsBackupSection
        bind:this={backupSection}
        bind:open={openSections.backup}
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
      />

    </div>

    {#if settingsDirty}
      <SettingsSaveBar
        labels={dirtySectionLabels}
        saving={savingAll}
        ondiscard={discardChanges}
        onsave={saveAll}
      />
    {/if}
  {/if}
</div>

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
  }
</style>
