<script>
  import Header from '$lib/components/Header.svelte';
  import Icon from '$lib/components/Icons.svelte';
</script>

<Header
  title="Help & Documentation"
  subtitle="Learn how to use Invoice Machine"
/>

<div class="page-content">
  <div class="help-sections">
    <!-- Getting Started -->
    <section class="help-section">
      <h2>
        <Icon name="home" size="md" />
        Getting Started
      </h2>
      <div class="help-content">
        <p>Welcome to Invoice Machine! Here's how to get set up:</p>
        <ol>
          <li>Go to <strong>Settings</strong> to configure your business profile</li>
          <li>Add your business name, address, and upload your logo</li>
          <li>Set your default payment terms and payment instructions</li>
          <li>Start creating invoices!</li>
        </ol>
      </div>
    </section>

    <!-- Creating Invoices -->
    <section class="help-section">
      <h2>
        <Icon name="invoice" size="md" />
        Creating Invoices
      </h2>
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
    </section>

    <!-- Invoice Numbering -->
    <section class="help-section">
      <h2>
        <Icon name="invoice" size="md" />
        Invoice Numbering
      </h2>
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
    </section>

    <!-- Managing Clients -->
    <section class="help-section">
      <h2>
        <Icon name="users" size="md" />
        Managing Clients
      </h2>
      <div class="help-content">
        <ul>
          <li><strong>Add Client:</strong> Go to Clients &gt; New Client</li>
          <li><strong>Edit Client:</strong> Click on a client to view and edit their details</li>
          <li><strong>Delete Client:</strong> Deleted clients go to Trash for 90 days before permanent deletion</li>
        </ul>
        <p>Client information is automatically populated when creating new invoices for that client.</p>
      </div>
    </section>

    <!-- PDF Generation -->
    <section class="help-section">
      <h2>
        <Icon name="download" size="md" />
        PDF Generation
      </h2>
      <div class="help-content">
        <ul>
          <li>Click <strong>Download PDF</strong> on any invoice or quote to download it</li>
          <li>PDFs are automatically regenerated if the invoice has been modified since the last generation</li>
          <li>Filename format: <code>[Client Name] - [Invoice Number].pdf</code></li>
        </ul>
        <p>The PDF includes your logo, business details, line items, totals, and payment instructions (if enabled).</p>
      </div>
    </section>

    <!-- Settings -->
    <section class="help-section">
      <h2>
        <Icon name="settings" size="md" />
        Settings
      </h2>
      <div class="help-content">
        <h3>Business Profile</h3>
        <p>Configure your company name, address, phone, email, and tax ID (EIN). This information appears on all invoices.</p>

        <h3>Logo</h3>
        <p>Upload your company logo. Supported formats: PNG, JPG, GIF, SVG, WebP. Maximum size: 5MB. Click the trash icon to remove your logo.</p>

        <h3>Default Payment Terms</h3>
        <p>Set the default number of days until an invoice is due. This is automatically applied to new invoices but can be changed per invoice.</p>

        <h3>Payment Methods</h3>
        <p>Add multiple payment options (Bank Transfer, Venmo, Zelle, PayPal, etc.) with their specific instructions. When creating invoices, you can select which payment methods to show on the PDF.</p>

        <h3>Legacy Payment Instructions</h3>
        <p>The "Default Payment Instructions" field is a fallback used when no payment methods are configured or selected.</p>

        <h3>Accent Color</h3>
        <p>Customize the accent color used in your invoices. The default is forest green (#16a34a).</p>

        <h3>Theme</h3>
        <p>Choose between light mode, dark mode, or system preference (which follows your operating system's setting).</p>
      </div>
    </section>

    <!-- Trash -->
    <section class="help-section">
      <h2>
        <Icon name="trash" size="md" />
        Trash
      </h2>
      <div class="help-content">
        <p>When you delete invoices or clients, they're moved to Trash instead of being permanently deleted.</p>
        <ul>
          <li>Items remain in Trash for <strong>90 days</strong></li>
          <li>Click <strong>Restore</strong> to recover an item</li>
          <li>Click <strong>Empty Trash</strong> to permanently delete items older than 90 days</li>
        </ul>
      </div>
    </section>

    <!-- Keyboard Shortcuts -->
    <section class="help-section">
      <h2>
        <Icon name="settings" size="md" />
        Tips
      </h2>
      <div class="help-content">
        <ul>
          <li>Use the sidebar to navigate between sections</li>
          <li>Click on any invoice row to view its details</li>
          <li>The theme toggle in the sidebar lets you switch between light and dark mode</li>
          <li>All monetary amounts use tabular figures for clean alignment</li>
        </ul>
      </div>
    </section>

    <!-- Data & Backup -->
    <section class="help-section">
      <h2>
        <Icon name="download" size="md" />
        Data & Backup
      </h2>
      <div class="help-content">
        <p>All your data is stored locally in the <code>data/</code> directory:</p>
        <ul>
          <li><code>invoicely.db</code> - SQLite database with all invoices, clients, and settings</li>
          <li><code>logos/</code> - Your uploaded logo files</li>
          <li><code>pdfs/</code> - Generated PDF files</li>
        </ul>
        <p>To backup your data, simply copy the entire <code>data/</code> directory.</p>
      </div>
    </section>

    <!-- MCP Integration -->
    <section class="help-section">
      <h2>
        <Icon name="check" size="md" />
        Claude Desktop (MCP) Integration
      </h2>
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
        <p>The MCP server provides 21 tools for full invoice management:</p>
        <ul>
          <li><strong>Profile:</strong> get/update profile, add/remove payment methods</li>
          <li><strong>Clients:</strong> list, get, create, update, delete, restore</li>
          <li><strong>Invoices:</strong> list, get, create, update, delete, restore</li>
          <li><strong>Line Items:</strong> add, update, remove</li>
          <li><strong>Other:</strong> generate PDF, list trash, empty trash</li>
        </ul>
      </div>
    </section>
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
    gap: var(--space-6);
  }

  .help-section {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
  }

  .help-section h2 {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: var(--space-4);
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--color-border-light);
  }

  .help-section h2 :global(.icon) {
    color: var(--color-primary);
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

    .help-section {
      padding: var(--space-4);
    }
  }
</style>
