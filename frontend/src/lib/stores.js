import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { request, setCsrfToken } from '$lib/api';

/**
 * @typedef {{ id: number, message: string, type: 'success' | 'error' | 'info' }} ToastMessage
 */

// ===== Auth Store =====

const DEFAULT_AUTH_STATE = {
  loading: false,
  authenticated: false,
  needsSetup: false,
  username: null,
  checkFailed: false,
};

function buildAuthState(data = {}) {
  return {
    ...DEFAULT_AUTH_STATE,
    authenticated: !!data.authenticated,
    needsSetup: !!data.needs_setup,
    username: data.username ?? null,
    checkFailed: false,
  };
}

function createAuthStore() {
  const { subscribe, set } = writable({
    ...DEFAULT_AUTH_STATE,
    loading: true,
  });

  return {
    subscribe,
    check: async () => {
      try {
        const data = await request('/auth/status');
        if (data?.csrf_token) setCsrfToken(data.csrf_token);
        set(buildAuthState(data));
        return data;
      } catch (e) {
        set({ ...DEFAULT_AUTH_STATE, checkFailed: true });
        return { authenticated: false, needs_setup: false, check_failed: true };
      }
    },
    login: async (username, password) => {
      const data = await request('/auth/login', {
        method: 'POST',
        body: { username, password },
      });
      set(buildAuthState({ authenticated: true, username: data.username }));
      return data;
    },
    setup: async (username, password) => {
      const data = await request('/auth/setup', {
        method: 'POST',
        body: { username, password },
      });
      set(buildAuthState({ authenticated: true, username: data.username }));
      return data;
    },
    logout: async () => {
      await request('/auth/logout', { method: 'POST' });
      set(DEFAULT_AUTH_STATE);
    },
    changePassword: async (currentPassword, newPassword) => {
      return request('/auth/password', {
        method: 'POST',
        body: { current_password: currentPassword, new_password: newPassword },
      });
    },
  };
}

export const auth = createAuthStore();

// ===== UI State =====

export const sidebarOpen = writable(false);

export const toggleSidebar = () => {
  sidebarOpen.update((open) => !open);
};

// ===== Theme Store =====

function applyTheme(theme) {
  if (!browser) return;

  const root = document.documentElement;
  root.classList.remove('light', 'dark');

  if (theme === 'light') {
    root.classList.add('light');
  } else if (theme === 'dark') {
    root.classList.add('dark');
  }
}

function persistTheme(theme) {
  if (browser) {
    localStorage.setItem('theme', theme);
  }
}

function getNextTheme(theme) {
  return theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system';
}

function createThemeStore() {
  const stored = browser ? localStorage.getItem('theme') : null;
  const initial = stored || 'system';

  const { subscribe, set, update } = writable(initial);

  if (browser) {
    applyTheme(initial);
  }

  return {
    subscribe,
    set: (value) => {
      persistTheme(value);
      applyTheme(value);
      set(value);
    },
    toggle: () => {
      update((current) => {
        const next = getNextTheme(current);
        persistTheme(next);
        applyTheme(next);
        return next;
      });
    },
  };
}

export const theme = createThemeStore();

// ===== Toast Notifications =====

function createToastStore() {
  /** @type {import('svelte/store').Writable<ToastMessage[]>} */
  const { subscribe, update } = writable([]);

  let nextId = 0;

  /** @param {string} message @param {'success' | 'error' | 'info'} [type='info'] */
  const show = (message, type = 'info') => {
    // Monotonic id so two toasts in the same millisecond don't collide.
    const id = ++nextId;
    update((toasts) => [...toasts, { id, message, type }]);

    // Errors linger so they can actually be read; others auto-dismiss quickly.
    const ttl = type === 'error' ? 8000 : 3000;
    setTimeout(() => {
      update((toasts) => toasts.filter((t) => t.id !== id));
    }, ttl);
  };

  return {
    subscribe,
    show,
    success: (message) => show(message, 'success'),
    error: (message) => show(message, 'error'),
    info: (message) => show(message, 'info'),
    dismiss: (id) => {
      update((toasts) => toasts.filter((t) => t.id !== id));
    },
  };
}

export const toast = createToastStore();

// ===== Formatters =====

export const formatCurrency = (amount, currency = 'USD') => {
  const num = typeof amount === 'string' ? parseFloat(amount) : Number(amount);
  const safe = Number.isFinite(num) ? num : 0;
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency || 'USD',
    }).format(safe);
  } catch {
    // Unknown/invalid currency code: fall back to amount + code.
    return `${safe.toFixed(2)} ${currency}`;
  }
};

export const formatDate = (dateStr, format = 'short') => {
  if (!dateStr) return '';
  // Accept both date-only ("2026-05-28") and full ISO datetimes
  // ("2026-05-28T12:00:00+00:00"); parse the date part as a local date to
  // avoid a UTC shift.
  const datePart = String(dateStr).split('T')[0];
  const [year, month, day] = datePart.split('-').map(Number);
  if (!year || !month || !day) return '';
  const date = new Date(year, month - 1, day);
  if (format === 'short') {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
};

