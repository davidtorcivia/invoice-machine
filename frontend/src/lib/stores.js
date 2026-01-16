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

export function createDataStore(fetchFn, initialValue = null) {
  const { subscribe, set, update } = writable(initialValue);
  const loading = createLoadingStore();
  const error = writable(null);

  const refresh = async (...args) => {
    error.set(null);
    try {
      const data = await loading.with(() => fetchFn(...args));
      set(data);
      return data;
    } catch (e) {
      error.set(e.message);
      toast.error(e.message);
      throw e;
    }
  };

  return {
    subscribe,
    set,
    update,
    loading: { subscribe: loading.subscribe },
    error: { subscribe: error.subscribe },
    refresh,
  };
}

// ===== Business Profile Store =====

export const profile = createDataStore(
  () => fetch('/api/profile').then((r) => r.json()),
  null
);

// ===== Client Store =====

export const clients = createDataStore(
  () => fetch('/api/clients').then((r) => r.json()),
  []
);

// ===== Invoice Store =====

export const invoices = createDataStore(
  () => fetch('/api/invoices').then((r) => r.json()),
  []
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
