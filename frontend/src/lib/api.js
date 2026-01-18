/**
 * API client for Invoicely backend
 */

const API_BASE = '/api';

/**
 * Make an API request
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;

  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const config = { ...defaultOptions, ...options };

  // Handle body
  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }

  const response = await fetch(url, config);

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || data.message || `Request failed: ${response.status}`);
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

    const response = await fetch(`${API_BASE}/profile/logo`, {
      method: 'POST',
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
};

// ===== Clients =====

export const clientsApi = {
  list: (params = {}) => {
    const search = new URLSearchParams();
    if (params.search) search.append('search', params.search);
    if (params.include_deleted) search.append('include_deleted', 'true');
    const query = search.toString() ? `?${search}` : '';
    return get(`/clients${query}`);
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
    const search = new URLSearchParams();
    if (params.status) search.append('status', params.status);
    if (params.client_id) search.append('client_id', params.client_id);
    if (params.from_date) search.append('from_date', params.from_date);
    if (params.to_date) search.append('to_date', params.to_date);
    if (params.include_deleted) search.append('include_deleted', 'true');
    search.append('limit', params.limit || '50');
    const query = search.toString() ? `?${search}` : '';
    return get(`/invoices${query}`);
  },

  get: (id) => get(`/invoices/${id}`),

  create: (data) => post('/invoices', data),

  update: (id, data) => put(`/invoices/${id}`, data),

  delete: (id) => del(`/invoices/${id}`),

  restore: (id) => post(`/invoices/${id}/restore`),

  addItem: (id, item) => {
    const params = new URLSearchParams();
    params.append('description', item.description);
    params.append('quantity', item.quantity);
    params.append('unit_price', item.unit_price);
    params.append('sort_order', item.sort_order || 0);
    return post(`/invoices/${id}/items?${params}`);
  },

  updateItem: (id, itemId, data) => put(`/invoices/${id}/items/${itemId}`, data),

  deleteItem: (id, itemId) => del(`/invoices/${id}/items/${itemId}`),

  generatePdf: (id) => post(`/invoices/${id}/generate-pdf`),

  getPdfUrl: (id) => `${API_BASE}/invoices/${id}/pdf`,
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
    const search = new URLSearchParams();
    if (params.client_id) search.append('client_id', params.client_id);
    if (params.active_only !== undefined) search.append('active_only', params.active_only);
    const query = search.toString() ? `?${search}` : '';
    return get(`/recurring${query}`);
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
};

// ===== Search =====

export const searchApi = {
  search: (query, params = {}) => {
    const search = new URLSearchParams();
    search.append('q', query);
    if (params.invoices !== undefined) search.append('invoices', params.invoices);
    if (params.clients !== undefined) search.append('clients', params.clients);
    if (params.limit) search.append('limit', params.limit);
    return get(`/search?${search}`);
  },
};

// ===== Analytics =====

export const analyticsApi = {
  getRevenue: (params = {}) => {
    const search = new URLSearchParams();
    if (params.from_date) search.append('from_date', params.from_date);
    if (params.to_date) search.append('to_date', params.to_date);
    if (params.group_by) search.append('group_by', params.group_by);
    const query = search.toString() ? `?${search}` : '';
    return get(`/analytics/revenue${query}`);
  },

  getClientLifetimeValues: (params = {}) => {
    const search = new URLSearchParams();
    if (params.client_id) search.append('client_id', params.client_id);
    if (params.limit) search.append('limit', params.limit);
    const query = search.toString() ? `?${search}` : '';
    return get(`/analytics/clients${query}`);
  },
};
