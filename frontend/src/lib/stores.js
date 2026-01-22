/**
 * Svelte stores for Invoice Machine
 */
import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';

// ===== Auth Store =====

function createAuthStore() {
  const { subscribe, set } = writable({
    loading: true,
    authenticated: false,
    needsSetup: false,
    username: null,
  });

  return {
    subscribe,
    check: async () => {
      try {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        set({
          loading: false,
          authenticated: data.authenticated,
          needsSetup: data.needs_setup,
          username: data.username,
        });
        return data;
      } catch (e) {
        set({ loading: false, authenticated: false, needsSetup: false, username: null });
        return { authenticated: false, needs_setup: false };
      }
    },
    login: async (username, password) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Login failed');
      }
      const data = await res.json();
      set({ loading: false, authenticated: true, needsSetup: false, username: data.username });
      return data;
    },
    setup: async (username, password) => {
      const res = await fetch('/api/auth/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Setup failed');
      }
      const data = await res.json();
      set({ loading: false, authenticated: true, needsSetup: false, username: data.username });
      return data;
    },
    logout: async () => {
      await fetch('/api/auth/logout', { method: 'POST' });
      set({ loading: false, authenticated: false, needsSetup: false, username: null });
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

function createThemeStore() {
  // Get initial value from localStorage or default to 'system'
  const stored = browser ? localStorage.getItem('theme') : null;
  const initial = stored || 'system';

  const { subscribe, set, update } = writable(initial);

  const applyTheme = (theme) => {
    if (!browser) return;

    const root = document.documentElement;
    root.classList.remove('light', 'dark');

    if (theme === 'light') {
      root.classList.add('light');
    } else if (theme === 'dark') {
      root.classList.add('dark');
    }
    // 'system' uses media query, no class needed
  };

  // Apply initial theme
  if (browser) {
    applyTheme(initial);
  }

  return {
    subscribe,
    set: (value) => {
      if (browser) {
        localStorage.setItem('theme', value);
      }
      applyTheme(value);
      set(value);
    },
    toggle: () => {
      update((current) => {
        // Cycle: system -> light -> dark -> system
        const next = current === 'system' ? 'light' : current === 'light' ? 'dark' : 'system';
        if (browser) {
          localStorage.setItem('theme', next);
        }
        applyTheme(next);
        return next;
      });
    },
  };
}

export const theme = createThemeStore();

// ===== Toast Notifications =====

function createToastStore() {
  const { subscribe, update } = writable([]);

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
  const { subscribe, set, update } = writable(false);

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
 * @param {Object} options - Configuration options
 * @param {boolean} options.lazy - If true (default), only fetch on first subscription
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
  (signal) => fetch('/api/profile', { signal }).then((r) => r.json()),
  null,
  { lazy: false } // Profile is needed for many pages
);

// ===== Client Store =====
// Clients are lazily loaded when first accessed

export const clients = createDataStore(
  (signal) => fetch('/api/clients', { signal }).then((r) => r.json()),
  [],
  { lazy: true }
);

// ===== Invoice Store =====
// Invoices are lazily loaded when first accessed

export const invoices = createDataStore(
  (signal) => fetch('/api/invoices', { signal }).then((r) => r.json()),
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
  const date = new Date(dateStr);
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
