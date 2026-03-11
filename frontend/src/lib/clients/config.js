export const clientSortOptions = [
  { value: 'created_at-desc', label: 'Newest first', field: 'created_at', dir: 'desc' },
  { value: 'created_at-asc', label: 'Oldest first', field: 'created_at', dir: 'asc' },
  { value: 'name-asc', label: 'Name (A-Z)', field: 'name', dir: 'asc' },
  { value: 'name-desc', label: 'Name (Z-A)', field: 'name', dir: 'desc' },
  { value: 'city-asc', label: 'City (A-Z)', field: 'city', dir: 'asc' },
  { value: 'city-desc', label: 'City (Z-A)', field: 'city', dir: 'desc' },
  { value: 'payment_terms-asc', label: 'Payment terms (shortest)', field: 'payment_terms', dir: 'asc' },
  { value: 'payment_terms-desc', label: 'Payment terms (longest)', field: 'payment_terms', dir: 'desc' }
];

const avatarColors = [
  { bg: '#dbeafe', fg: '#1d4ed8' },
  { bg: '#dcfce7', fg: '#15803d' },
  { bg: '#fef3c7', fg: '#b45309' },
  { bg: '#fce7f3', fg: '#be185d' },
  { bg: '#e0e7ff', fg: '#4338ca' },
  { bg: '#fed7aa', fg: '#c2410c' },
  { bg: '#d1fae5', fg: '#047857' },
  { bg: '#ede9fe', fg: '#6d28d9' },
  { bg: '#fecaca', fg: '#b91c1c' },
  { bg: '#ccfbf1', fg: '#0f766e' }
];

export function getAvatarColor(clientId) {
  return avatarColors[Number(clientId) % avatarColors.length];
}

export function createClientDraft() {
  return {
    name: '',
    business_name: '',
    email: '',
    phone: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: 'United States',
    payment_terms_days: 30,
    notes: '',
    preferred_currency: '',
    tax_override: false,
    tax_enabled: false,
    tax_rate: '',
    tax_name: 'Tax'
  };
}

export function applyClientToDraft(client) {
  return {
    name: client.name || '',
    business_name: client.business_name || '',
    email: client.email || '',
    phone: client.phone || '',
    address_line1: client.address_line1 || '',
    address_line2: client.address_line2 || '',
    city: client.city || '',
    state: client.state || '',
    postal_code: client.postal_code || '',
    country: client.country || '',
    payment_terms_days: client.payment_terms_days || 30,
    notes: client.notes || '',
    preferred_currency: client.preferred_currency || '',
    tax_override: client.tax_enabled !== null,
    tax_enabled: !!client.tax_enabled,
    tax_rate: client.tax_rate && parseFloat(client.tax_rate) > 0 ? client.tax_rate : '',
    tax_name: client.tax_name || 'Tax'
  };
}

export function buildClientPayload(draft, useNullTaxDefaults = false) {
  const payload = {
    name: draft.name || undefined,
    business_name: draft.business_name || undefined,
    email: draft.email || undefined,
    phone: draft.phone || undefined,
    address_line1: draft.address_line1 || undefined,
    address_line2: draft.address_line2 || undefined,
    city: draft.city || undefined,
    state: draft.state || undefined,
    postal_code: draft.postal_code || undefined,
    country: draft.country || undefined,
    payment_terms_days: Number(draft.payment_terms_days) || undefined,
    notes: draft.notes || undefined,
    preferred_currency: draft.preferred_currency || (useNullTaxDefaults ? null : undefined)
  };

  if (draft.tax_override) {
    payload.tax_enabled = draft.tax_enabled ? 1 : 0;
    payload.tax_rate = draft.tax_enabled && draft.tax_rate ? parseFloat(draft.tax_rate) : 0;
    payload.tax_name = draft.tax_name || 'Tax';
  } else if (useNullTaxDefaults) {
    payload.tax_enabled = null;
    payload.tax_rate = null;
    payload.tax_name = null;
  }

  return payload;
}
