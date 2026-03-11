export const DEFAULT_SETTINGS_SECTIONS = {
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

export function createProfileForm() {
  return {
    name: '',
    businessName: '',
    email: '',
    phone: '',
    addressLine1: '',
    addressLine2: '',
    city: '',
    state: '',
    postalCode: '',
    country: 'United States',
    ein: '',
    accentColor: '#16a34a',
    defaultPaymentTermsDays: 30,
    defaultCurrencyCode: 'USD',
    defaultNotes: '',
    defaultPaymentInstructions: '',
    defaultTaxEnabled: false,
    defaultTaxRate: '',
    defaultTaxName: 'Tax'
  };
}

export function createSmtpForm() {
  return {
    enabled: false,
    host: '',
    port: 587,
    username: '',
    password: '',
    fromEmail: '',
    fromName: '',
    useTls: true,
    passwordSet: false
  };
}

export function createBackupForm() {
  return {
    enabled: true,
    retentionDays: 30,
    s3Enabled: false,
    s3EndpointUrl: '',
    s3AccessKeyId: '',
    s3SecretAccessKey: '',
    s3Bucket: '',
    s3Region: '',
    s3Prefix: 'invoice-machine-backups'
  };
}

export function createApiAccessState() {
  return {
    mcpApiKey: '',
    mcpApiKeyConfigured: false,
    botApiKey: '',
    botApiKeyConfigured: false,
    appBaseUrl: ''
  };
}

export function createPaymentMethodDraft() {
  return {
    name: '',
    instructions: ''
  };
}

export function mapProfileToProfileForm(profile) {
  return {
    name: profile.name || '',
    businessName: profile.business_name || '',
    email: profile.email || '',
    phone: profile.phone || '',
    addressLine1: profile.address_line1 || '',
    addressLine2: profile.address_line2 || '',
    city: profile.city || '',
    state: profile.state || '',
    postalCode: profile.postal_code || '',
    country: profile.country || 'United States',
    ein: profile.ein || '',
    accentColor: profile.accent_color || '#16a34a',
    defaultPaymentTermsDays: profile.default_payment_terms_days || 30,
    defaultCurrencyCode: profile.default_currency_code || 'USD',
    defaultNotes: profile.default_notes || '',
    defaultPaymentInstructions: profile.default_payment_instructions || '',
    defaultTaxEnabled: profile.default_tax_enabled || false,
    defaultTaxRate: profile.default_tax_rate || '',
    defaultTaxName: profile.default_tax_name || 'Tax'
  };
}

export function mapSmtpSettingsToForm(settings) {
  return {
    enabled: settings.smtp_enabled || false,
    host: settings.smtp_host || '',
    port: settings.smtp_port || 587,
    username: settings.smtp_username || '',
    password: '',
    fromEmail: settings.smtp_from_email || '',
    fromName: settings.smtp_from_name || '',
    useTls: settings.smtp_use_tls !== false,
    passwordSet: settings.smtp_password_set || false
  };
}

export function mapBackupSettingsToForm(settings) {
  return {
    enabled: settings.backup_enabled,
    retentionDays: settings.backup_retention_days,
    s3Enabled: settings.backup_s3_enabled,
    s3EndpointUrl: settings.backup_s3_endpoint_url || '',
    s3AccessKeyId: '',
    s3SecretAccessKey: '',
    s3Bucket: settings.backup_s3_bucket || '',
    s3Region: settings.backup_s3_region || '',
    s3Prefix: settings.backup_s3_prefix || 'invoice-machine-backups'
  };
}

export function mapProfileToApiAccess(profile) {
  return {
    mcpApiKey: '',
    mcpApiKeyConfigured: !!profile.mcp_api_key_configured,
    botApiKey: '',
    botApiKeyConfigured: !!profile.bot_api_key_configured,
    appBaseUrl: profile.app_base_url || ''
  };
}

export function buildProfilePayload(form, paymentMethods, appBaseUrl) {
  return {
    name: form.name || undefined,
    business_name: form.businessName || undefined,
    email: form.email || undefined,
    phone: form.phone || undefined,
    address_line1: form.addressLine1 || undefined,
    address_line2: form.addressLine2 || undefined,
    city: form.city || undefined,
    state: form.state || undefined,
    postal_code: form.postalCode || undefined,
    country: form.country || undefined,
    ein: form.ein || undefined,
    accent_color: form.accentColor || undefined,
    default_payment_terms_days: Number(form.defaultPaymentTermsDays) || undefined,
    default_currency_code: form.defaultCurrencyCode || undefined,
    default_notes: form.defaultNotes || undefined,
    default_payment_instructions: form.defaultPaymentInstructions || undefined,
    payment_methods: paymentMethods,
    app_base_url: appBaseUrl || undefined,
    default_tax_enabled: form.defaultTaxEnabled,
    default_tax_rate: form.defaultTaxRate || undefined,
    default_tax_name: form.defaultTaxName || undefined
  };
}

export function buildSmtpPayload(form) {
  const data = {
    smtp_enabled: form.enabled,
    smtp_host: form.host || undefined,
    smtp_port: Number(form.port) || 587,
    smtp_username: form.username || undefined,
    smtp_from_email: form.fromEmail || undefined,
    smtp_from_name: form.fromName || undefined,
    smtp_use_tls: form.useTls
  };
  if (form.password) {
    data.smtp_password = form.password;
  }
  return data;
}

export function buildBackupPayload(form) {
  const data = {
    backup_enabled: form.enabled,
    backup_retention_days: Number(form.retentionDays) || 30,
    backup_s3_enabled: form.s3Enabled
  };

  if (form.s3Enabled) {
    data.backup_s3_endpoint_url = form.s3EndpointUrl || null;
    data.backup_s3_bucket = form.s3Bucket || null;
    data.backup_s3_region = form.s3Region || null;
    data.backup_s3_prefix = form.s3Prefix || null;
    if (form.s3AccessKeyId && !form.s3AccessKeyId.includes('*')) {
      data.backup_s3_access_key_id = form.s3AccessKeyId;
    }
    if (form.s3SecretAccessKey && !form.s3SecretAccessKey.includes('*')) {
      data.backup_s3_secret_access_key = form.s3SecretAccessKey;
    }
  }

  return data;
}

export function formatBackupBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export function formatBackupDate(isoString) {
  return new Date(isoString).toLocaleString();
}
