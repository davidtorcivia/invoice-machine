/**
 * Svelte stores for Invoice Machine
 */
import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { request } from '$lib/api';

/**
 * @typedef {{ id: number, message: string, type: 'success' | 'error' | 'info' }} ToastMessage
 */

// ===== Auth Store =====

const DEFAULT_AUTH_STATE = {
  loading: false,
  authenticated: false,
  needsSetup: false,
  username: null,
};

function buildAuthState(data = {}) {
  return {
    ...DEFAULT_AUTH_STATE,
    authenticated: !!data.authenticated,
    needsSetup: !!data.needs_setup,
    username: data.username ?? null,
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
        set(buildAuthState(data));
        return data;
      } catch (e) {
        set(DEFAULT_AUTH_STATE);
        return { authenticated: false, needs_setup: false };
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

  /** @param {string} message @param {'success' | 'error' | 'info'} [type='info'] */
  const show = (message, type = 'info') => {
    const id = Date.now();
    update((toasts) => [...toasts, { id, message, type }]);

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
      update((toasts) => toasts.filter((t) => t.id !== id));
    }, 3000);
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

// ===== Loading State =====

export const createLoadingStore = () => {
  const { subscribe, set } = writable(false);

  return {
    subscribe,
    set,
    with: async (fn) => {
      set(true);
      try {
        return await fn();
      } finally {
        set(false);
      }
    },
  };
};

// ===== Data Store =====

/**
 * Create a data store with lazy loading and request cancellation support.
 *
 * Features:
 * - Lazy loading: data is only fetched when first subscribed or explicitly refreshed
 * - Request cancellation: rapid refresh calls cancel previous in-flight requests
 * - Error handling: errors are captured and exposed via error store
 *
 * @param {Function} fetchFn - Async function to fetch data. Receives AbortSignal as first arg.
 * @param {*} initialValue - Initial value before first fetch
 * @param {{ lazy?: boolean }} [options={}] - Configuration options
 */
export function createDataStore(fetchFn, initialValue = null, options = {}) {
  const { lazy = true } = options;

  const { subscribe: rawSubscribe, set, update } = writable(initialValue);
  const loading = createLoadingStore();
  const error = writable(null);

  let hasFetched = false;
  let currentController = null;
  let subscriberCount = 0;

  // Wrap subscribe to trigger lazy loading on first subscriber
  const subscribe = (run, invalidate) => {
    subscriberCount++;

    // Trigger lazy load on first subscriber (if lazy mode and hasn't fetched)
    if (lazy && !hasFetched && subscriberCount === 1) {
      refresh().catch(() => {
        // Errors are already captured in error store
      });
    }

    const unsubscribe = rawSubscribe(run, invalidate);

    return () => {
      subscriberCount--;
      unsubscribe();
    };
  };

  const refresh = async (...args) => {
    // Cancel any in-flight request
    if (currentController) {
      currentController.abort();
    }

    // Create new abort controller for this request
    currentController = new AbortController();
    const signal = currentController.signal;

    error.set(null);
    try {
      const data = await loading.with(async () => {
        // Pass signal to fetchFn if it accepts it
        const result = await fetchFn(signal, ...args);
        return result;
      });

      // Only update if not aborted
      if (!signal.aborted) {
        set(data);
        hasFetched = true;
      }
      return data;
    } catch (e) {
      // Don't treat abort as an error
      if (e.name === 'AbortError') {
        return get({ subscribe: rawSubscribe });
      }
      error.set(e.message);
      toast.error(e.message);
      throw e;
    } finally {
      currentController = null;
    }
  };

  // Force refresh even if already fetched
  const forceRefresh = (...args) => {
    hasFetched = false;
    return refresh(...args);
  };

  // Reset store to initial state
  const reset = () => {
    hasFetched = false;
    set(initialValue);
    error.set(null);
  };

  return {
    subscribe,
    set,
    update,
    loading: { subscribe: loading.subscribe },
    error: { subscribe: error.subscribe },
    refresh,
    forceRefresh,
    reset,
    // Expose for testing
    get hasFetched() {
      return hasFetched;
    },
  };
}

// ===== Business Profile Store =====
// Profile is often needed early, so we don't use lazy loading for it

export const profile = createDataStore(
  (signal) => request('/profile', { signal }),
  null,
  { lazy: false } // Profile is needed for many pages
);

// ===== Client Store =====
// Clients are lazily loaded when first accessed

export const clients = createDataStore(
  (signal) => request('/clients', { signal }),
  [],
  { lazy: true }
);

// ===== Invoice Store =====
// Invoices are lazily loaded when first accessed

export const invoices = createDataStore(
  (signal) => request('/invoices', { signal }),
  [],
  { lazy: true }
);

// ===== Formatters =====

export const formatCurrency = (amount, currency = 'USD') => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (currency === 'USD') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(num);
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(num);
};

export const formatDate = (dateStr, format = 'short') => {
  // Parse YYYY-MM-DD as local date to avoid UTC timezone shift
  const [year, month, day] = dateStr.split('-').map(Number);
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

export const formatStatus = (status) => {
  const map = {
    draft: 'Draft',
    sent: 'Sent',
    paid: 'Paid',
    overdue: 'Overdue',
    cancelled: 'Cancelled',
  };
  return map[status] || status;
};

export const statusBadgeClass = (status) => {
  const map = {
    draft: 'badge-draft',
    sent: 'badge-sent',
    paid: 'badge-paid',
    overdue: 'badge-overdue',
    cancelled: 'badge-cancelled',
  };
  return map[status] || 'badge-draft';
};
