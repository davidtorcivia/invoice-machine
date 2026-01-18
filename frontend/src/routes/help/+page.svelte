<script>
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';

  // Track which sections are open
  let openSections = {
    gettingStarted: true,
    creatingInvoices: false,
    invoiceNumbering: false,
    managingClients: false,
    pdfGeneration: false,
    settings: false,
    taxSettings: false,
    recurringInvoices: false,
    emailDelivery: false,
    search: false,
    reportsAnalytics: false,
    trash: false,
    tips: false,
    dataBackup: false,
    mcpIntegration: false
  };
</script>

<Header
  title="Help & Documentation"
  subtitle="Learn how to use Invoice Machine"
/>

<div class="page-content">
  <div class="help-sections">
    <!-- Getting Started -->
    <CollapsibleSection title="Getting Started" icon="home" bind:open={openSections.gettingStarted}>
      <div class="help-content">
        <p>Welcome to Invoice Machine! Here's how to get set up:</p>
        <ol>
          <li>Go to <strong>Settings</strong> to configure your business profile</li>
          <li>Add your business name, address, and upload your logo</li>
          <li>Set your default payment terms and payment instructions</li>
          <li>Start creating invoices!</li>
        </ol>
      </div>
    </CollapsibleSection>

    <!-- Creating Invoices -->
    <CollapsibleSection title="Creating Invoices" icon="invoice" bind:open={openSections.creatingInvoices}>
      <div class="help-content">
        <h3>New Invoice</h3>
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
        <p>If no payment methods are configured, a simple "Include Payment Instructions" toggle is shown instead.</p>
      </div>
    </CollapsibleSection>

    <!-- Invoice Numbering -->
    <CollapsibleSection title="Invoice Numbering" icon="invoice" bind:open={openSections.invoiceNumbering}>
      <div class="help-content">
        <p>Invoices are automatically numbered using the format: <code>YYYYMMDD-N</code></p>
        <ul>
          <li>First invoice on June 23, 2025: <code>20250623-1</code></li>
          <li>Second invoice same day: <code>20250623-2</code></li>
          <li>First invoice next day: <code>20250624-1</code></li>
          <li>Quotes use: <code>Q-YYYYMMDD-N</code></li>
        </ul>
        <p class="note"><strong>Note:</strong> Changing an invoice's issue date will regenerate its number based on the new date.</p>
      </div>
    </CollapsibleSection>

    <!-- Managing Clients -->
    <CollapsibleSection title="Managing Clients" icon="users" bind:open={openSections.managingClients}>
      <div class="help-content">
        <ul>
          <li><strong>Add Client:</strong> Go to Clients &gt; New Client</li>
          <li><strong>Edit Client:</strong> Click on a client to view and edit their details</li>
          <li><strong>Delete Client:</strong> Deleted clients go to Trash for 90 days before permanent deletion</li>
        </ul>
        <p>Client information is automatically populated when creating new invoices for that client.</p>
      </div>
    </CollapsibleSection>

    <!-- PDF Generation -->
    <CollapsibleSection title="PDF Generation" icon="download" bind:open={openSections.pdfGeneration}>
      <div class="help-content">
        <ul>
          <li>Click <strong>Download PDF</strong> on any invoice or quote to download it</li>
          <li>PDFs are automatically regenerated if the invoice has been modified since the last generation</li>
          <li>Filename format: <code>[Client Name] - [Invoice Number].pdf</code></li>
        </ul>
        <p>The PDF includes your logo, business details, line items, totals, and payment instructions (if enabled).</p>
      </div>
    </CollapsibleSection>

    <!-- Settings -->
    <CollapsibleSection title="Settings Overview" icon="settings" bind:open={openSections.settings}>
      <div class="help-content">
        <h3>Business Profile</h3>
        <p>Configure your company name, address, phone, email, and tax ID (EIN). This information appears on all invoices.</p>

        <h3>Logo</h3>
        <p>Upload your company logo. Supported formats: PNG, JPG, GIF, WebP. Maximum size: 5MB. Click the trash icon to remove your logo.</p>

        <h3>Default Payment Terms</h3>
        <p>Set the default number of days until an invoice is due. This is automatically applied to new invoices but can be changed per invoice.</p>

        <h3>Payment Methods</h3>
        <p>Add multiple payment options (Bank Transfer, Venmo, Zelle, PayPal, etc.) with their specific instructions. When creating invoices, you can select which payment methods to show on the PDF.</p>

        <h3>Accent Color</h3>
        <p>Customize the accent color used in your invoices. The default is forest green (#16a34a).</p>

        <h3>Theme</h3>
        <p>Choose between light mode, dark mode, or system preference (which follows your operating system's setting).</p>
      </div>
    </CollapsibleSection>

    <!-- Tax Settings -->
    <CollapsibleSection title="Tax Settings" icon="invoice" bind:open={openSections.taxSettings}>
      <div class="help-content">
        <p>Invoice Machine supports optional tax with a cascade system:</p>
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
        </ol>
      </div>
    </CollapsibleSection>

    <!-- Recurring Invoices -->
    <CollapsibleSection title="Recurring Invoices" icon="repeat" bind:open={openSections.recurringInvoices}>
      <div class="help-content">
        <p>Set up recurring invoices for retainers, subscriptions, or regular services.</p>
        <h3>Creating a Schedule</h3>
        <ol>
          <li>Go to <strong>Recurring</strong> in the sidebar</li>
          <li>Click <strong>New Schedule</strong></li>
          <li>Select a client and configure:
            <ul>
              <li>Name (e.g., "Monthly Retainer")</li>
              <li>Frequency: daily, weekly, monthly, quarterly, or yearly</li>
              <li>Schedule day (1-31 for monthly, 0-6 for weekly)</li>
              <li>Line items and amounts</li>
            </ul>
          </li>
        </ol>
        <h3>Managing Schedules</h3>
        <ul>
          <li><strong>Pause/Resume:</strong> Temporarily stop or restart a schedule</li>
          <li><strong>Trigger Now:</strong> Generate an invoice immediately</li>
          <li><strong>Edit:</strong> Modify schedule details and line items</li>
        </ul>
        <p class="note"><strong>Note:</strong> Invoices are automatically generated at 2 AM UTC on the scheduled day.</p>
      </div>
    </CollapsibleSection>

    <!-- Email Delivery -->
    <CollapsibleSection title="Email Delivery" icon="send" bind:open={openSections.emailDelivery}>
      <div class="help-content">
        <p>Send invoices directly to clients via SMTP email.</p>
        <h3>Configuration</h3>
        <ol>
          <li>Go to <strong>Settings</strong> &gt; <strong>Email Configuration</strong></li>
          <li>Configure your SMTP server:
            <ul>
              <li>Host (e.g., smtp.gmail.com)</li>
              <li>Port (587 for TLS, 465 for SSL)</li>
              <li>Username and password</li>
              <li>From name and email address</li>
            </ul>
          </li>
          <li>Click <strong>Test Connection</strong> to verify settings</li>
        </ol>
        <h3>Sending Invoices</h3>
        <p>On any invoice, click <strong>Send Email</strong> to deliver the PDF to the client. Works with any SMTP provider (Gmail, SendGrid, Mailgun, etc.).</p>
      </div>
    </CollapsibleSection>

    <!-- Search -->
    <CollapsibleSection title="Search" icon="search" bind:open={openSections.search}>
      <div class="help-content">
        <p>Use the search bar in the sidebar to find invoices and clients quickly.</p>
        <ul>
          <li>Search by invoice number, client name, or notes</li>
          <li>Results include both invoices and clients</li>
          <li>Partial matches are supported using full-text search</li>
          <li>Press Enter or wait for results as you type</li>
        </ul>
      </div>
    </CollapsibleSection>

    <!-- Reports & Analytics -->
    <CollapsibleSection title="Reports & Analytics" icon="chart" bind:open={openSections.reportsAnalytics}>
      <div class="help-content">
        <p>View revenue insights and client metrics from the <strong>Reports</strong> page.</p>
        <h3>Revenue Dashboard</h3>
        <ul>
          <li>Total revenue, paid vs outstanding</li>
          <li>Monthly and yearly breakdowns</li>
          <li>Revenue trends over time</li>
        </ul>
        <h3>Client Insights</h3>
        <ul>
          <li>Top clients by total paid</li>
          <li>Lifetime value per client</li>
          <li>Invoice count and payment history</li>
        </ul>
      </div>
    </CollapsibleSection>

    <!-- Trash -->
    <CollapsibleSection title="Trash" icon="trash" bind:open={openSections.trash}>
      <div class="help-content">
        <p>When you delete invoices or clients, they're moved to Trash instead of being permanently deleted.</p>
        <ul>
          <li>Items remain in Trash for <strong>90 days</strong></li>
          <li>Click <strong>Restore</strong> to recover an item</li>
          <li>Click <strong>Empty Trash</strong> to permanently delete items older than 90 days</li>
        </ul>
      </div>
    </CollapsibleSection>

    <!-- Tips -->
    <CollapsibleSection title="Tips & Shortcuts" icon="settings" bind:open={openSections.tips}>
      <div class="help-content">
        <ul>
          <li>Use the sidebar to navigate between sections</li>
          <li>Click on any invoice row to view its details</li>
          <li>The theme toggle in the sidebar lets you switch between light and dark mode</li>
          <li>All monetary amounts use tabular figures for clean alignment</li>
        </ul>
      </div>
    </CollapsibleSection>

    <!-- Data & Backup -->
    <CollapsibleSection title="Data & Backup" icon="download" bind:open={openSections.dataBackup}>
      <div class="help-content">
        <p>All your data is stored locally in the <code>data/</code> directory:</p>
        <ul>
          <li><code>invoicely.db</code> - SQLite database with all invoices, clients, and settings</li>
          <li><code>logos/</code> - Your uploaded logo files</li>
          <li><code>pdfs/</code> - Generated PDF files</li>
        </ul>
        <p>To backup your data, simply copy the entire <code>data/</code> directory, or use the built-in backup feature in Settings.</p>
      </div>
    </CollapsibleSection>

    <!-- MCP Integration -->
    <CollapsibleSection title="Claude Desktop (MCP) Integration" icon="settings" bind:open={openSections.mcpIntegration}>
      <div class="help-content">
        <p>Invoice Machine supports the Model Context Protocol (MCP), allowing you to manage invoices through natural language with Claude Desktop.</p>

        <h3>Remote Setup (Recommended)</h3>
        <p>To connect Claude Desktop from any computer:</p>
        <ol>
          <li>Go to <strong>Settings</strong> in Invoice Machine</li>
          <li>Scroll to <strong>MCP Integration</strong> and click <strong>Generate API Key</strong></li>
          <li>Copy the configuration shown and add it to your Claude Desktop config file</li>
        </ol>
        <p><strong>Config file location:</strong></p>
        <ul>
          <li><strong>macOS:</strong> <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></li>
          <li><strong>Windows:</strong> <code>%APPDATA%\Claude\claude_desktop_config.json</code></li>
        </ul>
        <pre class="code-block">{`{
  "mcpServers": {
    "invoice-machine": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-server.com/mcp/sse",
        "--header",
        "Authorization: Bearer YOUR_API_KEY"
      ]
    }
  }
}`}</pre>
        <p>Replace <code>your-server.com</code> with your actual domain and <code>YOUR_API_KEY</code> with the key from Settings.</p>

        <h3>Local Setup (Docker)</h3>
        <p>If running locally with Docker, you can use stdio transport instead:</p>
        <pre class="code-block">{`{
  "mcpServers": {
    "invoice-machine": {
      "command": "docker",
      "args": ["exec", "-i", "invoice-machine", "python", "-m", "invoicely.mcp.server"]
    }
  }
}`}</pre>

        <h3>Example Commands</h3>
        <p>Once configured, you can ask Claude to:</p>
        <ul>
          <li>"Create an invoice for Acme Corp for 40 hours of consulting at $150/hour"</li>
          <li>"List all unpaid invoices from last month"</li>
          <li>"Create a quote for the Johnson project with 3 line items"</li>
          <li>"Mark invoice 20250115-1 as paid"</li>
          <li>"Generate PDF for invoice 20250115-2"</li>
          <li>"Add a Venmo payment method to my profile"</li>
        </ul>

        <h3>Available Tools</h3>
        <p>The MCP server provides 30+ tools for full invoice management:</p>
        <ul>
          <li><strong>Profile:</strong> get/update profile, add/remove payment methods</li>
          <li><strong>Clients:</strong> list, get, create, update, delete, restore</li>
          <li><strong>Invoices:</strong> list, get, create, update, delete, restore</li>
          <li><strong>Line Items:</strong> add, update, remove</li>
          <li><strong>Recurring:</strong> list, get, create, update, delete, pause, resume, trigger schedules</li>
          <li><strong>Search:</strong> full-text search across invoices and clients</li>
          <li><strong>Analytics:</strong> revenue summary, top clients, lifetime value</li>
          <li><strong>Email:</strong> send invoice email, test SMTP connection</li>
          <li><strong>Other:</strong> generate PDF, list trash, empty trash</li>
        </ul>
      </div>
    </CollapsibleSection>
  </div>
</div>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 800px;
  }

  .help-sections {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .help-content {
    color: var(--color-text-secondary);
    line-height: 1.7;
  }

  .help-content h3 {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--color-text);
    margin-top: var(--space-5);
    margin-bottom: var(--space-2);
  }

  .help-content h3:first-child {
    margin-top: 0;
  }

  .help-content p {
    margin-bottom: var(--space-3);
  }

  .help-content ul,
  .help-content ol {
    margin-bottom: var(--space-3);
    padding-left: var(--space-6);
  }

  .help-content li {
    margin-bottom: var(--space-2);
  }

  .help-content code {
    font-family: var(--font-mono);
    font-size: 0.875em;
    background: var(--color-bg-sunken);
    padding: 0.125em 0.375em;
    border-radius: var(--radius-sm);
    color: var(--color-primary);
  }

  .help-content strong {
    font-weight: 600;
    color: var(--color-text);
  }

  .help-content .note {
    background: var(--color-warning-light);
    color: var(--color-warning);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
    font-size: 0.875rem;
  }

  .help-content pre.code-block {
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    line-height: 1.5;
    margin: var(--space-3) 0;
  }

  .help-content a {
    color: var(--color-primary);
    text-decoration: none;
  }

  .help-content a:hover {
    text-decoration: underline;
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }
  }
</style>
