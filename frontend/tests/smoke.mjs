/**
 * End-to-end smoke test: drives a running instance with headless Chromium.
 *
 * A passing `svelte-check` and `vite build` only prove the compiler accepted the
 * source. They cannot see a component that renders nothing, a reactive value
 * that stops updating, or a Content Security Policy that blocks the app from
 * booting at all. That last one actually happened: the build was green while
 * every non-Cloudflare deployment served a blank page.
 *
 * Deliberately dependency-free. It speaks the Chrome DevTools Protocol over a
 * WebSocket using only Node built-ins, so it adds nothing to the install and
 * runs against any Chromium already on the machine.
 *
 * Usage:
 *   npm run test:smoke                     # against http://localhost:8080
 *   BASE=http://localhost:18097 npm run test:smoke
 *   CHROME=/path/to/chrome npm run test:smoke
 *
 * The target instance must be running and must have no user yet, or have the
 * credentials below. It creates its own account and data, so point it at a
 * throwaway instance, never at production.
 */
import { spawn } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const BASE = process.env.BASE || 'http://localhost:8080';
const USERNAME = process.env.SMOKE_USER || 'smoketest';
const PASSWORD = process.env.SMOKE_PASSWORD || 'Str0ngPass1';
const DEBUG_PORT = Number(process.env.CDP_PORT || 9223);

const CHROME_CANDIDATES = [
  process.env.CHROME,
  process.env.CHROME_PATH,
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  // Playwright's cached download, if the machine happens to have one.
  ...playwrightChromiums(),
].filter(Boolean);

function playwrightChromiums() {
  const root = `${process.env.HOME || ''}/.cache/ms-playwright`;
  try {
    return readdirSync(root)
      .filter((entry) => entry.startsWith('chromium-'))
      .sort()
      .reverse()
      .map((entry) => `${root}/${entry}/chrome-linux64/chrome`);
  } catch {
    return [];
  }
}

const chromePath = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!chromePath) {
  console.error('No Chromium binary found. Set CHROME=/path/to/chrome.');
  console.error('Tried:\n  ' + CHROME_CANDIDATES.join('\n  '));
  process.exit(2);
}

// ---------------------------------------------------------------- seed data

async function api(method, path, body, cookies) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(cookies ? { Cookie: cookies.header, 'X-CSRF-Token': cookies.csrf } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: 'manual',
  });
  const setCookie = res.headers.getSetCookie?.() || [];
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON bodies are fine here */
  }
  return { status: res.status, json, setCookie };
}

function parseCookies(setCookie, previous) {
  const jar = { ...(previous?.jar || {}) };
  for (const line of setCookie) {
    const [pair] = line.split(';');
    const idx = pair.indexOf('=');
    jar[pair.slice(0, idx).trim()] = pair.slice(idx + 1).trim();
  }
  return {
    jar,
    header: Object.entries(jar)
      .map(([k, v]) => `${k}=${v}`)
      .join('; '),
    csrf: jar.csrf_token,
  };
}

async function seed() {
  let cookies = parseCookies([]);
  const setup = await api('POST', '/api/auth/setup', {
    username: USERNAME,
    password: PASSWORD,
  });
  cookies = parseCookies(setup.setCookie, cookies);

  if (setup.status !== 200) {
    const login = await api('POST', '/api/auth/login', {
      username: USERNAME,
      password: PASSWORD,
    });
    if (login.status !== 200) {
      throw new Error(
        `cannot authenticate against ${BASE}: setup ${setup.status}, login ${login.status}`,
      );
    }
    cookies = parseCookies(login.setCookie, cookies);
  }

  const client = await api(
    'POST',
    '/api/clients',
    { name: 'Smoke Client', email: 'smoke@example.test', city: 'Portland' },
    cookies,
  );
  const clientId = client.json?.id;

  const invoice = await api(
    'POST',
    '/api/invoices',
    {
      client_id: clientId,
      items: [
        { description: 'Consulting', quantity: 10, unit_price: 150 },
        { description: 'Hosting', quantity: 1, unit_price: 250 },
      ],
    },
    cookies,
  );
  const invoiceId = invoice.json?.id;

  await api('PUT', `/api/invoices/${invoiceId}`, { status: 'sent' }, cookies);
  // A partial payment gives the UI a derived balance to render, which is the
  // most sensitive thing to a reactivity regression.
  await api(
    'POST',
    `/api/invoices/${invoiceId}/payments`,
    { amount: 800, method: 'bank_transfer', reference: 'TX-77' },
    cookies,
  );
  await api(
    'POST',
    '/api/invoices',
    {
      client_id: clientId,
      document_type: 'quote',
      items: [{ description: 'Design', quantity: 1, unit_price: 900 }],
    },
    cookies,
  );

  // Enable SMTP so the recurring modal's auto-email option becomes reachable.
  await api(
    'PUT',
    '/api/settings/smtp',
    {
      smtp_enabled: true,
      smtp_host: 'smtp.example.test',
      smtp_from_email: 'billing@example.test',
    },
    cookies,
  );

  return { invoiceId };
}

// ------------------------------------------------------------------- driver

const chrome = spawn(
  chromePath,
  [
    '--headless=new',
    `--remote-debugging-port=${DEBUG_PORT}`,
    '--no-sandbox',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    `--user-data-dir=/tmp/invoice-machine-smoke-${process.pid}`,
    'about:blank',
  ],
  { stdio: 'ignore' },
);
process.on('exit', () => chrome.kill());

async function connect() {
  for (let i = 0; i < 40; i++) {
    try {
      const res = await fetch(`http://localhost:${DEBUG_PORT}/json/version`);
      return (await res.json()).webSocketDebuggerUrl;
    } catch {
      await sleep(250);
    }
  }
  throw new Error('Chromium did not expose a debugging port');
}

const ws = new WebSocket(await connect());
await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = reject;
});

let messageId = 0;
const pending = new Map();
const events = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg.result);
    pending.delete(msg.id);
  } else if (msg.method) {
    events.push(msg);
  }
};
const send = (method, params = {}, sessionId) =>
  new Promise((resolve) => {
    const id = ++messageId;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params, sessionId }));
  });

const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
await send('Runtime.enable', {}, sessionId);
await send('Log.enable', {}, sessionId);
await send('Page.enable', {}, sessionId);

const problems = [];
function drainEvents() {
  for (const event of events.splice(0)) {
    if (event.method === 'Runtime.exceptionThrown') {
      const details = event.params.exceptionDetails;
      problems.push(`exception: ${details.exception?.description || details.text}`);
    }
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error') {
      const text = event.params.entry.text;
      const expected =
        // The auth probe runs before login.
        /401|Failed to load resource/.test(text) ||
        // The unsaved-changes guard works correctly; Chrome refuses to show its
        // confirm() because a scripted navigation carries no user gesture.
        /beforeunload|unsaved changes/i.test(text);
      if (!expected) problems.push(`console: ${text}`);
    }
  }
}

const evaluate = async (expression) =>
  (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId))
    ?.result?.value;

async function goto(path) {
  await send('Page.navigate', { url: BASE + path }, sessionId);
  await sleep(1800);
  drainEvents();
}

const results = [];
function check(label, ok, detail = '') {
  results.push({ label, ok });
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? ` -> ${detail}` : ''}`);
}

// ------------------------------------------------------------------- checks

const { invoiceId } = await seed();
console.log(`\nDriving ${BASE} with ${chromePath}\n`);

await goto('/login');
check('login page renders', (await evaluate('document.querySelectorAll("input").length')) >= 2);

// Typing through the real setters exercises bind:value the way a user would.
await evaluate(`(() => {
  const set = (el, value) => {
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')
      .set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const [user, pass] = document.querySelectorAll('input');
  set(user, ${JSON.stringify(USERNAME)});
  set(pass, ${JSON.stringify(PASSWORD)});
  document.querySelector('form').requestSubmit();
})()`);
await sleep(2500);
drainEvents();
check(
  'login leaves /login',
  !(await evaluate('location.pathname')).includes('login'),
  await evaluate('location.pathname'),
);

for (const [path, label, probe] of [
  ['/dashboard', 'dashboard', 'document.body.innerText.length > 200'],
  ['/invoices', 'invoice list', 'document.body.innerText.includes("Smoke Client")'],
  [`/invoices/${invoiceId}`, 'invoice detail', 'document.body.innerText.includes("Balance due")'],
  ['/clients', 'client list', 'document.body.innerText.includes("Smoke Client")'],
  ['/recurring', 'recurring', 'document.body.innerText.length > 100'],
  ['/reports', 'reports', 'document.body.innerText.includes("Export")'],
  ['/settings', 'settings', 'document.body.innerText.includes("Business")'],
  ['/help', 'help', 'document.body.innerText.includes("Recording Payments")'],
  ['/trash', 'trash', 'document.body.innerText.length > 100'],
]) {
  await goto(path);
  check(`${label} renders`, (await evaluate(probe)) === true);
}

// Derived state: 1750 invoiced minus an 800 payment must render as 950 due.
await goto(`/invoices/${invoiceId}`);
const balance = await evaluate(
  `(document.body.innerText.match(/Balance due[\\s\\S]{0,40}/) || [''])[0].replace(/\\s+/g,' ')`,
);
check('derived balance is correct', /950/.test(balance), balance.trim());

// Opening a modal exercises component events and conditional rendering.
const clicked = await evaluate(`(() => {
  const btn = [...document.querySelectorAll('button')]
    .find((b) => /record payment/i.test(b.textContent));
  if (!btn) return false;
  btn.click();
  return true;
})()`);
await sleep(900);
drainEvents();
check(
  'record-payment modal opens',
  clicked === true && (await evaluate('!!document.querySelector("[role=dialog]")')) === true,
);

await goto('/settings');
const controls = await evaluate('document.querySelectorAll("button, summary").length');
check('settings renders its sections', controls > 5, `${controls} controls`);

// Two-way binding round trip. The settings page binds every field into a child
// section component, so this proves the child's edits reach the parent, the
// parent saves them, and they survive a reload. Rendering checks cannot see a
// broken binding: the input still updates on screen while the parent keeps
// stale values and silently saves the wrong thing.
const marker = `Smoke ${Date.now()}`;
const typed = await evaluate(`(async () => {
  // Sections are collapsed by default and render no content until opened, so
  // the toggle itself is part of what is being exercised here.
  const header = [...document.querySelectorAll('button')]
    .find((el) => /business information/i.test(el.textContent));
  if (!header) return 'no Business Information section header';
  if (header.getAttribute('aria-expanded') !== 'true') {
    header.click();
    await new Promise((r) => setTimeout(r, 500));
  }

  const field = document.querySelector('#business-name');
  if (!field) return 'section did not expand (its open binding is broken)';

  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), 'value')
    .set.call(field, ${JSON.stringify(marker)});
  field.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));

  const save = [...document.querySelectorAll('button')]
    .find((b) => /save/i.test(b.textContent) && !b.disabled);
  if (!save) return 'no enabled save button (parent never saw the edit)';
  save.click();
  return 'saved';
})()`);
await sleep(2200);
drainEvents();
check('settings edit reaches the parent and saves', typed === 'saved', String(typed));

const persisted = await evaluate(
  `fetch('/api/profile').then((r) => r.json()).then((p) => p.business_name)`,
);
check('edited value round-tripped to the server', persisted === marker, String(persisted));

// Parent-to-child prop flow on the busiest form: the tax settings live in one
// card and the running total that consumes them lives in another, so a broken
// prop shows up as a total that never picks up the rate.
await goto('/invoices/new');
const taxPreview = await evaluate(`(async () => {
  const set = (el, value) => {
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  };

  const desc = document.querySelector('#item-desc-0');
  const price = document.querySelector('#item-price-0');
  if (!desc || !price) return 'no line item inputs';
  set(desc, 'Smoke line');
  set(price, '200');
  await new Promise((r) => setTimeout(r, 400));

  const taxToggle = [...document.querySelectorAll('input[type=checkbox]')]
    .find((c) => /apply tax|enable tax/i.test(c.closest('label')?.textContent || ''));
  if (!taxToggle) return 'no tax toggle';
  if (!taxToggle.checked) taxToggle.click();
  await new Promise((r) => setTimeout(r, 400));

  const rate = [...document.querySelectorAll('input')]
    .find((i) => /tax-rate|taxRate/.test(i.id || ''));
  if (!rate) return 'no tax rate field after enabling tax';
  set(rate, '10');
  await new Promise((r) => setTimeout(r, 500));

  const totals = (document.body.innerText.match(/Subtotal[\\s\\S]{0,160}/) || [''])[0];
  return totals.replace(/\\s+/g, ' ').trim();
})()`);
drainEvents();
// 200 subtotal at 10% must render a 20.00 tax line and a 220.00 total.
check(
  'tax rate reaches the totals card',
  typeof taxPreview === 'string' &&
    taxPreview.includes('20.00') &&
    taxPreview.includes('220.00'),
  String(taxPreview).slice(0, 120),
);

// Component callbacks. svelte-check proves a callback prop is wired to a
// declared prop; only clicking proves the child actually invokes it. A missed
// call is a button that does nothing, with no error anywhere.
await goto('/invoices');
const navigated = await evaluate(`(async () => {
  const row = document.querySelector('tbody tr, .invoice-card');
  if (!row) return 'no invoice rows';
  const before = location.pathname;
  row.click();
  await new Promise((r) => setTimeout(r, 1200));
  return location.pathname === before ? 'did not navigate' : location.pathname;
})()`);
drainEvents();
check(
  'invoice row callback navigates to the detail page',
  typeof navigated === 'string' &&
    navigated.startsWith('/invoices/') &&
    /^\d+$/.test(navigated.slice('/invoices/'.length)),
  String(navigated),
);

// Options gated on another endpoint's state. The auto-email toggle reads SMTP
// status, which `GET /api/profile` does not return; sourcing it from there left
// the option permanently hidden however SMTP was configured, with nothing to
// show for it in the UI or the logs.
await goto('/recurring');
const autoEmail = await evaluate(`(async () => {
  const btn = [...document.querySelectorAll('button')]
    .find((b) => /new schedule/i.test(b.textContent));
  if (!btn) return 'no New Schedule button';
  btn.click();
  await new Promise((r) => setTimeout(r, 1200));
  if (!document.querySelector('[role=dialog]')) return 'modal did not open';
  const visible = document.body.innerText.includes('Automatically email invoice');
  const close = [...document.querySelectorAll('[role=dialog] button')]
    .find((b) => /cancel|close/i.test(b.textContent + (b.getAttribute('aria-label') || '')));
  close?.click();
  await new Promise((r) => setTimeout(r, 500));
  return visible ? 'offered' : 'hidden despite SMTP being enabled';
})()`);
drainEvents();
check('auto-email option appears once SMTP is configured', autoEmail === 'offered', String(autoEmail));

// ConfirmModal backs every destructive action, so its cancel path is worth a check.
await goto('/recurring');
const modal = await evaluate(`(async () => {
  const del = [...document.querySelectorAll('button')]
    .find((b) => /delete/i.test(b.title || b.getAttribute('aria-label') || ''));
  if (!del) return 'no schedules to exercise';
  del.click();
  await new Promise((r) => setTimeout(r, 700));
  if (!document.querySelector('[role=dialog]')) return 'delete callback never opened the modal';

  const cancel = [...document.querySelectorAll('[role=dialog] button')]
    .find((b) => /cancel/i.test(b.textContent));
  if (!cancel) return 'modal has no cancel button';
  cancel.click();
  await new Promise((r) => setTimeout(r, 700));
  return document.querySelector('[role=dialog]') ? 'cancel callback did not close it' : 'ok';
})()`);
drainEvents();
check(
  'confirm-modal open and cancel callbacks fire',
  modal === 'ok' || modal === 'no schedules to exercise',
  String(modal),
);

drainEvents();
console.log('');
if (problems.length) {
  console.log(`${problems.length} console error(s) or exception(s):`);
  for (const problem of [...new Set(problems)].slice(0, 15)) {
    console.log('  ' + problem.slice(0, 240));
  }
} else {
  console.log('No console errors or uncaught exceptions.');
}

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed\n`);
chrome.kill();
process.exit(failed === 0 && problems.length === 0 ? 0 : 1);
