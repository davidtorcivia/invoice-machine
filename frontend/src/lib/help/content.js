export const helpSections = [
  {
    key: 'gettingStarted',
    title: 'Getting Started',
    icon: 'home',
    content: `<p>Welcome to Invoice Machine! Here's how to get set up:</p>
<ol>
  <li>Go to <strong>Settings</strong> to configure your business profile</li>
  <li>Add your business name, address, and upload your logo</li>
  <li>Set your default payment terms, currency, and payment instructions</li>
  <li>Click <strong>Save Changes</strong> in the bar that appears at the bottom of the screen</li>
  <li>Start creating invoices!</li>
</ol>`
  },
  {
    key: 'creatingInvoices',
    title: 'Creating Invoices',
    icon: 'invoice',
    content: `<h3>New Invoice</h3>
<ol>
  <li>Navigate to <strong>Invoices</strong> &gt; <strong>New Invoice</strong></li>
  <li>Select an existing client or enter new client details</li>
  <li>Add line items with descriptions, quantities/hours, and prices</li>
  <li>Set the issue date and due date</li>
  <li>Click <strong>Create Invoice</strong></li>
</ol>
<h3>Creating a Quote</h3>
<p>To create a quote instead of an invoice:</p>
<ol>
  <li>Check the <strong>This is a Quote</strong> checkbox at the top of the form</li>
  <li>Fill in the details as you would for an invoice</li>
  <li>Quotes are numbered separately using the format Q-YYYYMMDD-N</li>
</ol>
<p>When a quote is accepted, open it and click <strong>Convert to Invoice</strong>. This creates a new invoice carrying the quote's line items, tax, and currency. The quote itself is kept exactly as the client saw it, and the two documents link to each other, so you always have a record of what was agreed. A quote can only be converted once.</p>
<h3>Currency</h3>
<p>Each invoice can use its own currency. The default comes from Settings, and each client can have a preferred currency that is applied automatically.</p>
<h3>Reference / PO Number</h3>
<p>Use the client reference field to record a purchase order or job number with the invoice.</p>
<h3>Hours vs Quantity</h3>
<p>Each line item can be set to either "Qty" or "Hours" using the Type dropdown. This changes the column header in the PDF to reflect the appropriate unit.</p>
<h3>Payment Methods</h3>
<p>You can configure multiple payment methods in Settings (e.g., Bank Transfer, Venmo, Zelle) and select which ones to include on each invoice:</p>
<ol>
  <li>Go to <strong>Settings</strong> and scroll to <strong>Payment Methods</strong></li>
  <li>Add each payment option with its name and instructions</li>
  <li>When creating an invoice, check the payment methods to include</li>
  <li>The PDF will show only the selected methods with their details</li>
</ol>
<p>If no payment methods are configured, a simple "Include Payment Instructions" toggle is shown instead.</p>`
  },
  {
    key: 'invoiceNumbering',
    title: 'Invoice Numbering',
    icon: 'invoice',
    content: `<p>Invoices are automatically numbered using the format: <code>YYYYMMDD-N</code></p>
<ul>
  <li>First invoice on June 23, 2025: <code>20250623-1</code></li>
  <li>Second invoice same day: <code>20250623-2</code></li>
  <li>First invoice next day: <code>20250624-1</code></li>
  <li>Quotes use: <code>Q-YYYYMMDD-N</code></li>
</ul>
<p class="note"><strong>Note:</strong> Changing an invoice's issue date will regenerate its number based on the new date.</p>`
  },
  {
    key: 'invoiceWorkflow',
    title: 'Invoice Statuses & Workflow',
    icon: 'check',
    content: `<p>Invoices move through a status lifecycle: <strong>Draft</strong> &rarr; <strong>Sent</strong> &rarr; <strong>Paid</strong>, with <strong>Overdue</strong> and <strong>Cancelled</strong> as needed. Quotes use Draft, Sent, and Cancelled.</p>
<h3>Changing Status</h3>
<ul>
  <li>Open an invoice and use the status selector at the top, or the <strong>Mark as Sent</strong> / <strong>Mark as Paid</strong> shortcut buttons</li>
  <li>Marking an invoice paid records the payment date, which is used in reports</li>
  <li>Sent invoices past their due date are automatically marked <strong>Overdue</strong> once a day</li>
</ul>
<h3>Bulk Actions</h3>
<p>On the Invoices list, select multiple invoices with the checkboxes to <strong>Mark Sent</strong>, <strong>Mark Paid</strong>, or <strong>Delete</strong> them in one step.</p>
<h3>Filtering & Pagination</h3>
<p>The Invoices list can be filtered by status, client, document type (invoice/quote), and date. Filters and the current page are reflected in the URL, so you can bookmark or share a filtered view. The Clients list is paginated the same way.</p>`
  },
  {
    key: 'recordingPayments',
    title: 'Recording Payments',
    icon: 'dollar',
    content: `<p>Record what clients actually pay, including partial payments, from the <strong>Payments</strong> panel on any invoice.</p>
<h3>Recording a Payment</h3>
<ol>
  <li>Open the invoice and click <strong>Record payment</strong></li>
  <li>Enter the amount, the date it arrived, and how it was paid</li>
  <li>Add a bank reference or cheque number if you have one</li>
</ol>
<p>The amount defaults to the full balance due, so settling an invoice in full is one click.</p>
<h3>Partial Payments</h3>
<p>An invoice can take as many payments as it needs. It shows a running balance and a progress bar, and moves to <strong>Paid</strong> on its own once the payments cover the total. Delete a payment and it reverts to Sent or Overdue, whichever is correct for its due date.</p>
<p>Paying more than the balance is refused unless you tick <strong>record as overpayment</strong>, which guards against a mistyped amount.</p>
<h3>What You Are Owed</h3>
<p>The <strong>Reports</strong> page has an accounts receivable table showing outstanding balances grouped by how far past due they are: not yet due, 1-30 days, 31-60, 61-90, and over 90. Amounts in different currencies are listed separately and never added together.</p>`
  },
  {
    key: 'onlinePayments',
    title: 'Getting Paid Online',
    icon: 'external',
    content: `<p>Connect a Stripe account and each invoice gets a payment link, so clients can pay by card instead of arranging a transfer.</p>
<h3>Setup</h3>
<ol>
  <li>In Stripe, create a <strong>restricted API key</strong> with write access to Checkout Sessions</li>
  <li>Paste it into <strong>Settings</strong> &gt; <strong>Online payments</strong> and enable payments</li>
  <li>In Stripe, add a webhook pointing at the URL shown in that settings panel, subscribed to <code>checkout.session.completed</code></li>
  <li>Paste the webhook signing secret back into Settings</li>
</ol>
<p class="note"><strong>Why a restricted key:</strong> it can create checkouts and nothing else, so a leaked value cannot move money or read your customer list. Both the key and the signing secret are encrypted before they are stored and are never shown again.</p>
<h3>Using It</h3>
<p>Open an invoice and click <strong>Create payment link</strong>. The link covers whatever is still outstanding, appears on the PDF, and can be included in emails with the <code>{payment_link}</code> placeholder. When a client pays, the payment is recorded against the invoice automatically and the balance updates.</p>
<p>Which cards and wallets appear at checkout is controlled from your Stripe dashboard, not here.</p>
<p>Without the webhook secret, links still work but completed payments will not be recorded back, so you would have to enter them by hand.</p>`
  },
  {
    key: 'paymentReminders',
    title: 'Payment Reminders',
    icon: 'clock',
    content: `<p>Chase unpaid invoices without having to remember to. Configure this in <strong>Settings</strong> &gt; <strong>Payment reminders</strong>.</p>
<h3>Setting a Schedule</h3>
<p>A schedule is a list of days relative to the due date. Negative numbers are before it, positive numbers after. The default is three days before, then one, seven, and fourteen days after.</p>
<h3>Timing</h3>
<p>Set your timezone and the hour you want reminders to go out. Both the send time and the count of days until due follow your local clock, so a reminder never lands in the middle of the night or a day out.</p>
<h3>What Gets Chased</h3>
<ul>
  <li>Only invoices that are sent or overdue and still owe something</li>
  <li>Each point in the schedule is sent at most once per invoice</li>
  <li>Fully paid invoices are never chased; partially paid ones are chased for the balance</li>
  <li>Turning reminders on for an already-overdue invoice sends one current reminder, not the whole backlog</li>
</ul>
<p>Reminder emails have their own subject and body templates, which additionally accept <code>{amount_due}</code>, <code>{due_status}</code>, and <code>{days_overdue}</code>. Use <strong>Send due reminders now</strong> to run the sweep immediately and see what goes out.</p>
<p class="note"><strong>Note:</strong> SMTP has to be configured first, since there is otherwise no way to send them.</p>`
  },
  {
    key: 'managingClients',
    title: 'Managing Clients',
    icon: 'users',
    content: `<ul>
  <li><strong>Add Client:</strong> Go to Clients &gt; New Client</li>
  <li><strong>Edit Client:</strong> Click on a client to view and edit their details</li>
  <li><strong>Delete Client:</strong> Deleted clients go to Trash for 90 days before permanent deletion</li>
</ul>
<p>Client information is automatically populated when creating new invoices for that client.</p>`
  },
  {
    key: 'pdfGeneration',
    title: 'PDF Generation',
    icon: 'download',
    content: `<ul>
  <li>Click <strong>Download PDF</strong> on any invoice or quote to download it</li>
  <li>PDFs are regenerated only when the document has actually changed, and served straight from disk otherwise</li>
  <li>Filename format: <code>[Client Name] - [Invoice Number].pdf</code></li>
</ul>
<p>The PDF includes your logo, business details, line items, totals, and payment instructions if enabled. Once payments are recorded it also shows what has been paid and the remaining balance, and it carries the online payment link when one exists.</p>`
  },
  {
    key: 'settings',
    title: 'Settings Overview',
    icon: 'settings',
    content: `<h3>Saving Changes</h3>
<p>When you edit any setting, a <strong>Save Changes</strong> bar appears at the bottom of the screen showing which sections have unsaved changes. Click <strong>Save Changes</strong> to save everything at once, or <strong>Discard</strong> to revert. Logo uploads and API key actions apply immediately and don't need saving.</p>
<h3>Business Profile</h3>
<p>Configure your company name, address, phone, email, and tax ID (EIN). This information appears on all invoices.</p>
<h3>Logo</h3>
<p>Upload your company logo. Supported formats: PNG/JPEG, GIF, WebP. Maximum size: 5MB. Click the trash icon to remove your logo.</p>
<h3>Invoice Defaults</h3>
<p>Set the default payment terms (days until due), default currency, default notes, and payment instructions. These are applied to new invoices but can be changed per invoice.</p>
<h3>Payment Methods</h3>
<p>Add multiple payment options (Bank Transfer, Venmo, Zelle, PayPal, etc.) with their specific instructions. When creating invoices, you can select which payment methods to show on the PDF.</p>
<h3>Accent Color</h3>
<p>Customize the accent color used in your invoices. The default is forest green (#16a34a).</p>
<h3>Theme</h3>
<p>Choose between light mode, dark mode, or system preference (which follows your operating system's setting).</p>
<h3>Payments, Reminders &amp; Exchange Rates</h3>
<p>Further down the page you will find <strong>Payment reminders</strong> for automated chasing, <strong>Online payments</strong> for accepting cards through Stripe, and <strong>Exchange rates</strong> for combining multiple currencies in reports. Each has its own help section here.</p>
<h3>API Keys</h3>
<p>Settings includes two separate keys: <strong>MCP API Key</strong> for Claude Desktop (<code>/mcp/*</code>) and <strong>Bot API Key</strong> for REST automation (<code>/api/*</code>).</p>`
  },
  {
    key: 'taxSettings',
    title: 'Tax Settings',
    icon: 'invoice',
    content: `<p>Invoice Machine supports optional tax with a cascade system:</p>
<ol>
  <li><strong>Invoice-level:</strong> Override tax settings on individual invoices</li>
  <li><strong>Client-level:</strong> Set default tax for specific clients</li>
  <li><strong>Global default:</strong> Configure in Settings &gt; Tax Settings</li>
</ol>
<p>The cascade priority is: Invoice &gt; Client &gt; Global. Tax is disabled by default.</p>
<h3>Enabling Tax</h3>
<ol>
  <li>Go to <strong>Settings</strong> and scroll to <strong>Tax Settings</strong></li>
  <li>Enable tax and set your default rate (e.g., 8.5%)</li>
  <li>Optionally set per-client rates in the client editor</li>
  <li>Override on specific invoices as needed</li>
</ol>`
  },
  {
    key: 'recurringInvoices',
    title: 'Recurring Invoices',
    icon: 'repeat',
    content: `<p>Set up recurring invoices for retainers, subscriptions, or regular services.</p>
<h3>Creating a Schedule</h3>
<ol>
  <li>Go to <strong>Recurring</strong> in the sidebar</li>
  <li>Click <strong>New Schedule</strong></li>
  <li>Select a client and configure a name, frequency, schedule timing, and line items</li>
</ol>
<h3>Managing Schedules</h3>
<ul>
  <li><strong>Pause/Resume:</strong> Temporarily stop or restart a schedule</li>
  <li><strong>Trigger Now:</strong> Generate an invoice immediately</li>
  <li><strong>Edit:</strong> Modify schedule details and line items</li>
</ul>
<p class="note"><strong>Note:</strong> Invoices are automatically generated at 2 AM UTC on the scheduled day.</p>`
  },
  {
    key: 'emailDelivery',
    title: 'Email Delivery',
    icon: 'send',
    content: `<p>Send invoices directly to clients via SMTP email.</p>
<h3>Configuration</h3>
<ol>
  <li>Go to <strong>Settings</strong> &gt; <strong>Email Settings (SMTP)</strong></li>
  <li>Configure your SMTP server host, port, credentials, and sender identity</li>
  <li>Click <strong>Test Connection</strong> to verify settings (this also saves them)</li>
</ol>
<h3>Email Templates</h3>
<p>Click <strong>Configure Email Templates</strong> in the SMTP section to customize the default subject and body used for invoice emails, with placeholders for details like the invoice number and client name.</p>
<h3>Sending Invoices</h3>
<p>On any invoice, click <strong>Send Email</strong> to deliver the PDF to the client. Works with any SMTP provider (Gmail, SendGrid, Mailgun, etc.).</p>`
  },
  {
    key: 'search',
    title: 'Search',
    icon: 'search',
    content: `<p>Use the search bar in the sidebar to find things quickly.</p>
<ul>
  <li>Covers invoice numbers, client names, notes, and line item descriptions</li>
  <li>Results are grouped into invoices, clients, and line items</li>
  <li>Partial matches are supported using full-text search</li>
  <li>Results appear as you type</li>
</ul>
<p>Searching line item text is the quickest way to answer questions like "what did I charge for that logo design last year".</p>`
  },
  {
    key: 'reportsAnalytics',
    title: 'Reports & Analytics',
    icon: 'chart',
    content: `<p>View revenue insights and client metrics from the <strong>Reports</strong> page.</p>
<h3>Revenue</h3>
<ul>
  <li>Invoiced, paid, outstanding, and overdue for the selected year</li>
  <li>Breakdown by month, quarter, or year</li>
</ul>
<h3>Accounts Receivable</h3>
<p>Outstanding balances bucketed by how far past due they are, with the individual overdue invoices listed underneath so you know exactly who to chase.</p>
<h3>Client Insights</h3>
<ul>
  <li>Top clients by total paid</li>
  <li>Lifetime value per client</li>
  <li>Invoice count and first and last invoice dates</li>
</ul>
<h3>Export</h3>
<p>Download the selected year as CSV: invoices, individual line items, payments, or clients. Amounts are written as plain numbers with a separate currency column, which is what spreadsheets and accounting software expect.</p>`
  },
  {
    key: 'multiCurrency',
    title: 'Multiple Currencies',
    icon: 'dollar',
    content: `<p>Each invoice carries its own currency, taken from the client's preference or your default. Totals throughout the app are reported per currency and are never added together, because adding dollars to euros produces a number that means nothing.</p>
<h3>One Headline Number</h3>
<p>If you do want a single combined figure, add exchange rates in <strong>Settings</strong> &gt; <strong>Exchange rates</strong>. Enter what one unit of each foreign currency is worth in your base currency.</p>
<p>The rate is copied onto each invoice when it is issued, so historical invoices keep the rate that applied at the time and old figures do not shift when today's rate moves. The Reports page then shows a converted roll-up.</p>
<p class="note"><strong>Note:</strong> invoices in a currency you have no rate for are left out of that roll-up and reported as excluded, so a partial total is never presented as a complete one.</p>`
  },
  {
    key: 'trash',
    title: 'Trash',
    icon: 'trash',
    content: `<p>When you delete invoices or clients, they're moved to Trash instead of being permanently deleted.</p>
<ul>
  <li>Items remain in Trash for <strong>90 days</strong>, then are purged automatically</li>
  <li>Click <strong>Restore</strong> to recover an item</li>
  <li>Click <strong>Empty Trash</strong> to permanently delete <strong>everything</strong> in the trash right away, regardless of age</li>
</ul>
<p class="note"><strong>Note:</strong> Emptying the trash also deletes the generated PDFs for those invoices. It cannot be undone, so take a backup first if you are unsure.</p>`
  },
  {
    key: 'tips',
    title: 'Tips & Shortcuts',
    icon: 'settings',
    content: `<ul>
  <li>Use the sidebar to navigate between sections</li>
  <li>Click on any invoice row to view its details</li>
  <li>The theme toggle in the sidebar lets you switch between light and dark mode</li>
  <li>All monetary amounts use tabular figures for clean alignment</li>
</ul>`
  },
  {
    key: 'dataBackup',
    title: 'Data & Backup',
    icon: 'download',
    content: `<p>All your data is stored locally in the <code>data/</code> directory:</p>
<ul>
  <li><code>invoice_machine.db</code> - SQLite database with all invoices, clients, and settings</li>
  <li><code>logos/</code> - Your uploaded logo files</li>
  <li><code>pdfs/</code> - Generated PDF files</li>
</ul>
<h3>Backups</h3>
<p>Manage backups in <strong>Settings</strong> &gt; <strong>Backup &amp; Restore</strong>:</p>
<ul>
  <li><strong>Automatic backups</strong> run daily; old backups are pruned after the configured retention period</li>
  <li><strong>Create Backup</strong> takes a manual backup at any time</li>
  <li>Optionally upload backups to <strong>S3-compatible storage</strong> (AWS S3, Backblaze B2, MinIO, etc.)</li>
  <li>Each backup can be <strong>downloaded</strong>, <strong>restored</strong>, or deleted from the list; restoring creates a pre-restore backup automatically and brings the schema up to date, so a backup from an older release comes back usable</li>
</ul>
<p class="note"><strong>Note:</strong> a backup contains your database and your uploaded logo. Generated PDFs are left out because they are rebuilt from the database whenever they are needed.</p>`
  },
  {
    key: 'mcpIntegration',
    title: 'Claude Desktop (MCP) Integration',
    icon: 'settings',
    content: `<p>Invoice Machine supports the Model Context Protocol (MCP), allowing you to manage invoices through natural language with Claude Desktop or claude.ai.</p>
<h3>Remote Setup (Recommended)</h3>
<ol>
  <li>Go to <strong>Settings</strong> in Invoice Machine</li>
  <li>Scroll to <strong>MCP Integration</strong> and click <strong>Generate API Key</strong></li>
  <li>Copy the configuration shown and add it to your Claude Desktop config file</li>
</ol>
<p>The server uses the MCP <strong>Streamable HTTP</strong> transport at <code>/mcp</code>. Each call is an independent request, so the connection survives proxy timeouts and server restarts. Clients that support remote MCP servers directly (such as claude.ai custom connectors) can use the endpoint URL with the Bearer token — no <code>mcp-remote</code> needed.</p>
<p><strong>Config file location:</strong></p>
<ul>
  <li><strong>macOS:</strong> <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></li>
  <li><strong>Windows:</strong> <code>%APPDATA%\\Claude\\claude_desktop_config.json</code></li>
</ul>
<h3>Protocol Version</h3>
<p>Invoice Machine implements MCP spec <strong>2026-07-28</strong> and answers every earlier revision from the same endpoint, so there is nothing to configure — new and old clients both connect.</p>
<p>Under this revision there is no session and no connection handshake: each request carries everything the server needs. That is what lets the endpoint sit behind a tunnel or proxy that drops idle connections without breaking your session. The tool list is also cacheable now, so clients stop re-fetching it on every reconnect.</p>
<p>The older SSE endpoint at <code>/mcp/sse</code> still works for existing configs, but it is deprecated in the MCP spec — point new clients at <code>/mcp</code>.</p>
<h3>What Claude Can and Cannot Do On Its Own</h3>
<p>Every tool is labelled so Claude knows which are safe lookups and which change something. Reading invoices, listing clients and running reports change nothing. Creating, editing and deleting are marked as changes, and anything that leaves the app — sending an email, testing your SMTP connection — is marked as reaching the outside world.</p>
<p>Two actions <strong>ask you first</strong>, because they cannot be undone:</p>
<ul>
  <li>Emailing an invoice to a client</li>
  <li>Triggering a recurring schedule early</li>
</ul>
<p>The confirmation names the actual recipient or schedule, and saying no stops it. If your client does not support these prompts, nothing breaks — it falls back to its own approval flow.</p>
<p>Recording a payment is protected against duplicates: each one carries a key, so if Claude retries a call that already went through, you get the payment you already had rather than a second one. Paying the same amount twice on purpose still works — that is a different key.</p>
<h3>Resources and Prompts</h3>
<p>Some data is readable directly, without Claude having to search for it: an invoice by its number (<code>invoice://20250115-1</code>), a client, everything currently outstanding, and your business profile.</p>
<p>Clients with a prompt picker also offer three shortcuts: <strong>Draft an invoice</strong>, <strong>Chase overdue invoices</strong>, and <strong>Month-end summary</strong>. All three draft and report only — they never send anything without you.</p>`
  },
  {
    key: 'botApiIntegration',
    title: 'Bot API Integration',
    icon: 'settings',
    content: `<p>For automation tools and scripts, generate a <strong>Bot API Key</strong> in Settings and use it with the REST API.</p>
<ul>
  <li>Send the key as a bearer token to <code>/api/*</code> endpoints</li>
  <li>Keep the key secret and rotate it if you suspect exposure</li>
  <li>Use the Settings page to revoke and regenerate access at any time</li>
</ul>`
  }
];
