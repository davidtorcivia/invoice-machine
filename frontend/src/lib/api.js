/**
 * API client for Invoice Machine backend
 */

const API_BASE = '/api';

export function getCsrfToken() {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

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
 */
export async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;

  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const headers = { ...defaultOptions.headers, ...(options.headers || {}) };
  const method = (options.method || 'GET').toUpperCase();

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  const config = { ...defaultOptions, ...options, headers };

  // Handle body
  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }

  const response = await fetch(url, config);

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : null;

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `Request failed: ${response.status}`);
  }

  return data;
}

/**
 * GET request
 */
function get(endpoint) {
  return request(endpoint, { method: 'GET' });
}

/**
 * POST request
 */
function post(endpoint, body) {
  return request(endpoint, { method: 'POST', body });
}

/**
 * PUT request
 */
function put(endpoint, body) {
  return request(endpoint, { method: 'PUT', body });
}

/**
 * DELETE request
 */
function del(endpoint) {
  return request(endpoint, { method: 'DELETE' });
}

// ===== Business Profile =====

export const profileApi = {
  get: () => get('/profile'),

  update: (data) => put('/profile', data),

  uploadLogo: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const csrfToken = getCsrfToken();
    const headers = csrfToken ? { 'X-CSRF-Token': csrfToken } : {};

    const response = await fetch(`${API_BASE}/profile/logo`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      throw new Error('Failed to upload logo');
    }

    return response.json();
  },

  deleteLogo: () => del('/profile/logo'),

  generateMcpKey: () => post('/profile/mcp-key'),

  deleteMcpKey: () => del('/profile/mcp-key'),

  generateBotKey: () => post('/profile/bot-key'),

  deleteBotKey: () => del('/profile/bot-key'),
};

// ===== Clients =====

export const clientsApi = {
  list: (params = {}) => {
    return get(
      `/clients${buildQuery({
        search: params.search,
        include_deleted: params.include_deleted ? 'true' : undefined,
        sort_by: params.sort_by,
        sort_dir: params.sort_dir,
      })}`
    );
  },

  get: (id) => get(`/clients/${id}`),

  create: (data) => post('/clients', data),

  update: (id, data) => put(`/clients/${id}`, data),

  delete: (id) => del(`/clients/${id}`),

  restore: (id) => post(`/clients/${id}/restore`),
};

// ===== Invoices =====

export const invoicesApi = {
  list: (params = {}) => {
    return get(
      `/invoices${buildQuery({
        status: params.status,
        document_type: params.document_type,
        client_id: params.client_id,
        from_date: params.from_date,
        to_date: params.to_date,
        include_deleted: params.include_deleted ? 'true' : undefined,
        sort_by: params.sort_by,
        sort_dir: params.sort_dir,
        limit: params.limit || 100,
      })}`
    );
  },

  listPaginated: (params = {}) => {
    return get(
      `/invoices/paginated${buildQuery({
        status: params.status,
        document_type: params.document_type,
        client_id: params.client_id,
        from_date: params.from_date,
        to_date: params.to_date,
        include_deleted: params.include_deleted ? 'true' : undefined,
        sort_by: params.sort_by,
        sort_dir: params.sort_dir,
        page: params.page || 1,
        per_page: params.per_page || 25,
      })}`
    );
  },

  get: (id) => get(`/invoices/${id}`),

  create: (data) => post('/invoices', data),

  update: (id, data) => put(`/invoices/${id}`, data),

  delete: (id) => del(`/invoices/${id}`),

  restore: (id) => post(`/invoices/${id}/restore`),

  addItem: (id, item) => {
    return post(
      `/invoices/${id}/items${buildQuery({
        description: item.description,
        quantity: item.quantity,
        unit_type: item.unit_type || 'qty',
        unit_price: item.unit_price,
        sort_order: item.sort_order || 0,
      })}`
    );
  },

  updateItem: (id, itemId, data) => put(`/invoices/${id}/items/${itemId}`, data),

  deleteItem: (id, itemId) => del(`/invoices/${id}/items/${itemId}`),

  generatePdf: (id) => post(`/invoices/${id}/generate-pdf`),

  getPdfUrl: (id) => `${API_BASE}/invoices/${id}/pdf`,

  bulkAction: (action, invoiceIds) => post('/invoices/bulk', {
    action,
    invoice_ids: invoiceIds,
  }),
};

// ===== Trash =====

export const trashApi = {
  list: () => get('/trash'),

  empty: () => post('/trash/empty'),

  restore: (type, id) => post(`/trash/restore/${type}/${id}`),
};

// ===== Backups =====

export const backupsApi = {
  getSettings: () => get('/backups/settings'),

  updateSettings: (data) => put('/backups/settings', data),

  list: (includeS3 = true) => get(`/backups?include_s3=${includeS3}`),

  create: (compress = true) => post(`/backups?compress=${compress}`),

  restore: (filename, downloadFromS3 = false) =>
    post(`/backups/restore/${encodeURIComponent(filename)}?download_from_s3=${downloadFromS3}`),

  download: (filename) => `${API_BASE}/backups/download/${encodeURIComponent(filename)}`,

  delete: (filename) => del(`/backups/${encodeURIComponent(filename)}`),

  cleanup: () => post('/backups/cleanup'),

  testS3: () => post('/backups/test-s3'),
};

// ===== Recurring Schedules =====

export const recurringApi = {
  list: (params = {}) => {
    return get(
      `/recurring${buildQuery({
        client_id: params.client_id,
        active_only: params.active_only,
      })}`
    );
  },

  get: (id) => get(`/recurring/${id}`),

  create: (data) => post('/recurring', data),

  update: (id, data) => put(`/recurring/${id}`, data),

  delete: (id) => del(`/recurring/${id}`),

  trigger: (id) => post(`/recurring/${id}/trigger`),
};

// ===== Email/SMTP =====

export const emailApi = {
  getSmtpSettings: () => get('/settings/smtp'),

  updateSmtpSettings: (data) => put('/settings/smtp', data),

  testSmtp: () => post('/settings/smtp/test'),

  sendInvoice: (invoiceId, data = {}) => post(`/invoices/${invoiceId}/send-email`, data),

  // Email templates
  getTemplates: () => get('/settings/email-templates'),

  updateTemplates: (data) => put('/settings/email-templates', data),

  previewEmail: (invoiceId, data = {}) => post(`/invoices/${invoiceId}/email-preview`, data),
};

// ===== Search =====

export const searchApi = {
  search: (query, params = {}) => {
    return get(
      `/search${buildQuery({
        q: query,
        invoices: params.invoices,
        clients: params.clients,
        limit: params.limit,
      })}`
    );
  },
};

// ===== Analytics =====

export const analyticsApi = {
  getDashboardSummary: () => get('/analytics/dashboard'),

  getRevenue: (params = {}) => {
    return get(
      `/analytics/revenue${buildQuery({
        from_date: params.from_date,
        to_date: params.to_date,
        group_by: params.group_by,
      })}`
    );
  },

  getClientLifetimeValues: (params = {}) => {
    return get(
      `/analytics/clients${buildQuery({
        client_id: params.client_id,
        limit: params.limit,
      })}`
    );
  },
};
