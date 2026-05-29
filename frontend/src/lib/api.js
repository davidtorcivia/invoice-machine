/**
 * API client for Invoice Machine backend
 */

import { browser } from '$app/environment';

const API_BASE = '/api';

/**
 * Handle an expired/invalid session (HTTP 401) by sending the user to the login
 * page. A hard navigation re-runs the layout's auth.check on load, which keeps
 * the auth store in sync and avoids the login<->app redirect bounce. No redirect
 * for the auth endpoints themselves (the login form handles its own 401).
 *
 * @param {string} endpoint
 */
function handleUnauthorized(endpoint) {
  if (!browser) return;
  if (endpoint.startsWith('/auth/')) return;
  const path = window.location.pathname;
  if (path === '/login' || path === '/setup') return;
  window.location.assign('/login');
}

/**
 * @typedef {string | number | boolean | null | undefined} QueryValue
 */

/**
 * @typedef {Record<string, QueryValue>} QueryParams
 */

/**
 * @typedef {{
 *   method?: string,
 *   headers?: HeadersInit,
 *   body?: BodyInit | Record<string, unknown> | null,
 *   signal?: AbortSignal,
 *   credentials?: RequestCredentials,
 *   mode?: RequestMode,
 *   cache?: RequestCache,
 *   redirect?: RequestRedirect,
 *   referrerPolicy?: ReferrerPolicy,
 *   integrity?: string,
 *   keepalive?: boolean
 * }} ApiRequestOptions
 */

/**
 * @param {HeadersInit | undefined} headers
 * @returns {Record<string, string>}
 */
function normalizeHeaders(headers) {
  if (!headers) return {};
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return { ...headers };
}

/**
 * @param {unknown} body
 * @returns {body is Record<string, unknown>}
 */
function isJsonBody(body) {
  return !!body && typeof body === 'object' && !(body instanceof FormData);
}

/**
 * @param {QueryValue} value
 */
function booleanQuery(value) {
  return value ? 'true' : undefined;
}

/**
 * @param {string} endpoint
 * @param {QueryParams} [params={}]
 */
function withQuery(endpoint, params = {}) {
  return `${endpoint}${buildQuery(params)}`;
}

/**
 * @param {string} basePath
 * @param {(params: QueryParams) => QueryParams} [buildListParams]
 */
function createCrudApi(basePath, buildListParams) {
  return {
    list: (params = {}) => get(withQuery(basePath, buildListParams ? buildListParams(params) : params)),
    get: (id) => get(`${basePath}/${id}`),
    create: (data) => post(basePath, data),
    update: (id, data) => put(`${basePath}/${id}`, data),
    delete: (id) => del(`${basePath}/${id}`),
  };
}

export function getCsrfToken() {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * @param {QueryParams} [params={}]
 */
export function buildQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, `${value}`);
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

/**
 * Make an API request
 *
 * @param {string} endpoint
 * @param {ApiRequestOptions} [options={}]
 */
export async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;

  /** @type {Record<string, string>} */
  const headers = {
    ...normalizeHeaders(options.headers),
  };
  const method = (options.method || 'GET').toUpperCase();

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  /** @type {ApiRequestOptions} */
  const config = { ...options, headers };

  if (isJsonBody(config.body)) {
    headers['Content-Type'] ||= 'application/json';
    config.body = JSON.stringify(config.body);
  }

  /** @type {RequestInit} */
  const fetchConfig = {
    ...config,
    // Always send cookies (session + CSRF), even if the API is ever served
    // from a different origin than the SPA.
    credentials: config.credentials ?? 'same-origin',
    body: config.body ?? undefined,
  };
  const response = await fetch(url, fetchConfig);

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : null;

  if (!response.ok) {
    // Session expired / not authenticated -> bounce to login.
    if (response.status === 401) {
      handleUnauthorized(endpoint);
    }
    throw new Error(
      data?.detail || data?.message || response.statusText || `Request failed: ${response.status}`
    );
  }

  return data;
}

/**
 * GET request
 *
 * @param {string} endpoint
 */
function get(endpoint) {
  return request(endpoint, { method: 'GET' });
}

/**
 * POST request
 *
 * @param {string} endpoint
 * @param {BodyInit | Record<string, unknown> | null} [body]
 */
function post(endpoint, body) {
  return request(endpoint, { method: 'POST', body });
}

/**
 * PUT request
 *
 * @param {string} endpoint
 * @param {BodyInit | Record<string, unknown> | null} [body]
 */
function put(endpoint, body) {
  return request(endpoint, { method: 'PUT', body });
}

/**
 * DELETE request
 *
 * @param {string} endpoint
 */
function del(endpoint) {
  return request(endpoint, { method: 'DELETE' });
}

// ===== Business Profile =====

export const profileApi = {
  get: () => get('/profile'),

  /** @param {Record<string, unknown>} data */
  update: (data) => put('/profile', data),

  /** @param {File} file */
  uploadLogo: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request('/profile/logo', { method: 'POST', body: formData });
  },

  deleteLogo: () => del('/profile/logo'),

  generateMcpKey: () => post('/profile/mcp-key'),

  deleteMcpKey: () => del('/profile/mcp-key'),

  generateBotKey: () => post('/profile/bot-key'),

  deleteBotKey: () => del('/profile/bot-key'),
};

// ===== Clients =====

export const clientsApi = {
  ...createCrudApi('/clients', (params) => ({
    search: params.search,
    include_deleted: booleanQuery(params.include_deleted),
    sort_by: params.sort_by,
    sort_dir: params.sort_dir,
  })),
  listPaginated: (params = {}) =>
    get(withQuery('/clients/paginated', {
      search: params.search,
      include_deleted: booleanQuery(params.include_deleted),
      sort_by: params.sort_by,
      sort_dir: params.sort_dir,
      page: params.page || 1,
      per_page: params.per_page || 24,
    })),
  restore: (id) => post(`/clients/${id}/restore`),
};

// ===== Invoices =====

export const invoicesApi = {
  ...createCrudApi('/invoices', (params) => ({
    status: params.status,
    document_type: params.document_type,
    client_id: params.client_id,
    from_date: params.from_date,
    to_date: params.to_date,
    include_deleted: booleanQuery(params.include_deleted),
    sort_by: params.sort_by,
    sort_dir: params.sort_dir,
    limit: params.limit || 100,
  })),
  listPaginated: (params = {}) =>
    get(withQuery('/invoices/paginated', {
      status: params.status,
      document_type: params.document_type,
      client_id: params.client_id,
      from_date: params.from_date,
      to_date: params.to_date,
      include_deleted: booleanQuery(params.include_deleted),
      sort_by: params.sort_by,
      sort_dir: params.sort_dir,
      page: params.page || 1,
      per_page: params.per_page || 25,
    })),
  restore: (id) => post(`/invoices/${id}/restore`),

  /** @param {number | string} id @param {{description?: string, quantity?: number, unit_type?: string, unit_price?: string | number, sort_order?: number}} item */
  addItem: (id, item) =>
    post(withQuery(`/invoices/${id}/items`, {
      description: item.description,
      quantity: item.quantity,
      unit_type: item.unit_type || 'qty',
      unit_price: item.unit_price,
      sort_order: item.sort_order || 0,
    })),

  /** @param {number | string} id @param {number | string} itemId @param {Record<string, unknown>} data */
  updateItem: (id, itemId, data) => put(`/invoices/${id}/items/${itemId}`, data),

  /** @param {number | string} id @param {number | string} itemId */
  deleteItem: (id, itemId) => del(`/invoices/${id}/items/${itemId}`),

  /** @param {number | string} id */
  generatePdf: (id) => post(`/invoices/${id}/generate-pdf`),

  /** @param {number | string} id */
  getPdfUrl: (id) => `${API_BASE}/invoices/${id}/pdf`,

  /** @param {string} action @param {Array<number | string>} invoiceIds */
  bulkAction: (action, invoiceIds) => post('/invoices/bulk', {
    action,
    invoice_ids: invoiceIds,
  }),
};

// ===== Trash =====

export const trashApi = {
  list: () => get('/trash'),

  empty: () => post('/trash/empty'),

  /** @param {string} type @param {number | string} id */
  restore: (type, id) => post(`/trash/restore/${type}/${id}`),
};

// ===== Backups =====

export const backupsApi = {
  getSettings: () => get('/backups/settings'),

  /** @param {Record<string, unknown>} data */
  updateSettings: (data) => put('/backups/settings', data),

  /** @param {boolean} [includeS3=true] */
  list: (includeS3 = true) => get(withQuery('/backups', { include_s3: includeS3 })),

  /** @param {boolean} [compress=true] */
  create: (compress = true) => post(withQuery('/backups', { compress })),

  /** @param {string} filename @param {boolean} [downloadFromS3=false] */
  restore: (filename, downloadFromS3 = false) =>
    post(withQuery(`/backups/restore/${encodeURIComponent(filename)}`, { download_from_s3: downloadFromS3 })),

  /** @param {string} filename */
  download: (filename) => `${API_BASE}/backups/download/${encodeURIComponent(filename)}`,

  /** @param {string} filename */
  delete: (filename) => del(`/backups/${encodeURIComponent(filename)}`),

  cleanup: () => post('/backups/cleanup'),

  testS3: () => post('/backups/test-s3'),
};

// ===== Recurring Schedules =====

export const recurringApi = {
  ...createCrudApi('/recurring', (params) => ({
    client_id: params.client_id,
    active_only: params.active_only,
  })),
  trigger: (id) => post(`/recurring/${id}/trigger`),
};

// ===== Email/SMTP =====

export const emailApi = {
  getSmtpSettings: () => get('/settings/smtp'),

  /** @param {Record<string, unknown>} data */
  updateSmtpSettings: (data) => put('/settings/smtp', data),

  testSmtp: () => post('/settings/smtp/test'),

  /** @param {number | string} invoiceId @param {Record<string, unknown>} [data={}] */
  sendInvoice: (invoiceId, data = {}) => post(`/invoices/${invoiceId}/send-email`, data),

  // Email templates
  getTemplates: () => get('/settings/email-templates'),

  /** @param {Record<string, unknown>} data */
  updateTemplates: (data) => put('/settings/email-templates', data),

  /** @param {number | string} invoiceId @param {Record<string, unknown>} [data={}] */
  previewEmail: (invoiceId, data = {}) => post(`/invoices/${invoiceId}/email-preview`, data),
};

// ===== Search =====

export const searchApi = {
  /** @param {string} query @param {QueryParams} [params={}] */
  search: (query, params = {}) => get(withQuery('/search', {
    q: query,
    invoices: params.invoices,
    clients: params.clients,
    limit: params.limit,
  })),
};

// ===== Analytics =====

export const analyticsApi = {
  getDashboardSummary: () => get('/analytics/dashboard'),

  /** @param {QueryParams} [params={}] */
  getRevenue: (params = {}) => get(withQuery('/analytics/revenue', {
    from_date: params.from_date,
    to_date: params.to_date,
    group_by: params.group_by,
  })),

  /** @param {QueryParams} [params={}] */
  getClientLifetimeValues: (params = {}) => get(withQuery('/analytics/clients', {
    client_id: params.client_id,
    limit: params.limit,
  })),
};
