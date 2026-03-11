<script>
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';

  export let mcpOpen = false;
  export let botOpen = false;
  export let appBaseUrl = '';
  export let mcpEndpointUrl = '';
  export let mcpApiKeyConfigured = false;
  export let mcpApiKey = '';
  export let generatingMcpKey = false;
  export let copyMcpKey;
  export let openDeleteMcpModal;
  export let generateMcpKey;
  export let botApiKeyConfigured = false;
  export let botApiKey = '';
  export let generatingBotKey = false;
  export let copyBotKey;
  export let openDeleteBotModal;
  export let generateBotKey;
</script>

<CollapsibleSection title="MCP Integration" subtitle="Claude Desktop remote access" icon="settings" bind:open={mcpOpen}>
  <p class="form-hint mb-4">
    Enable remote access to Invoice Machine via Claude Desktop using the Model Context Protocol (MCP).
    Generate an API key to allow secure connections from another computer.
  </p>

  <div class="form-group">
    <label for="app-base-url" class="label">Application URL</label>
    <input
      id="app-base-url"
      type="url"
      class="input"
      placeholder="https://invoices.example.com"
      bind:value={appBaseUrl}
    />
    <p class="form-hint">
      Set this to your public URL (e.g., Cloudflare Tunnel URL). Used for MCP connections and PDF links.
      Leave empty to use the current browser URL.
    </p>
  </div>

  {#if mcpApiKeyConfigured}
    <div class="mcp-status mcp-enabled">
      <div class="mcp-status-icon">
        <Icon name="check" size="md" />
      </div>
      <div class="mcp-status-info">
        <span class="mcp-status-label">Remote access enabled</span>
        <span class="mcp-status-endpoint">Endpoint: <code>{mcpEndpointUrl}/mcp/sse</code></span>
      </div>
    </div>

    <div class="mcp-key-display">
      <label class="label" for="mcp-api-key">API Key</label>
      <div class="mcp-key-row">
        <input id="mcp-api-key" type="password" class="input" value={mcpApiKey || '••••••••••••••••'} readonly />
        <button type="button" class="btn btn-secondary" on:click={copyMcpKey} disabled={!mcpApiKey}>
          <Icon name="copy" size="sm" />
          Copy
        </button>
      </div>
      {#if !mcpApiKey}
        <p class="form-hint">Key is hidden after generation. Regenerate to copy again.</p>
      {/if}
    </div>

    <div class="mcp-actions">
      <button type="button" class="btn btn-secondary" on:click={generateMcpKey} disabled={generatingMcpKey}>
        <Icon name="refresh" size="sm" />
        Regenerate Key
      </button>
      <button type="button" class="btn btn-ghost btn-danger-text" on:click={openDeleteMcpModal}>
        <Icon name="trash" size="sm" />
        Disable Remote Access
      </button>
    </div>
  {:else}
    <div class="mcp-status mcp-disabled">
      <div class="mcp-status-icon">
        <Icon name="x" size="md" />
      </div>
      <div class="mcp-status-info">
        <span class="mcp-status-label">Remote access disabled</span>
        <span class="mcp-status-hint">Generate an API key to enable Claude Desktop connections</span>
      </div>
    </div>

    <button type="button" class="btn btn-primary" on:click={generateMcpKey} disabled={generatingMcpKey}>
      <Icon name="plus" size="sm" />
      {generatingMcpKey ? 'Generating...' : 'Generate API Key'}
    </button>
  {/if}

  <div class="mcp-help mt-4">
    <details>
      <summary>How to configure Claude Desktop</summary>
      <div class="mcp-help-content">
        <p>Add this to your Claude Desktop config file:</p>
        <pre class="code-block">{`{
  "mcpServers": {
    "invoice-machine": {
      "transport": "sse",
      "url": "${mcpEndpointUrl}/mcp/sse",
      "headers": {
        "Authorization": "Bearer ${mcpApiKey || 'YOUR_API_KEY'}"
      }
    }
  }
}`}</pre>
        <p class="mt-2"><strong>Config file location:</strong></p>
        <ul>
          <li><strong>macOS:</strong> <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></li>
          <li><strong>Windows:</strong> <code>%APPDATA%\Claude\claude_desktop_config.json</code></li>
        </ul>
      </div>
    </details>
  </div>
</CollapsibleSection>

<CollapsibleSection title="Bot API Key" subtitle="REST API automation access" icon="settings" bind:open={botOpen}>
  <p class="form-hint mb-4">
    Generate a separate API key for conventional REST API access with bots and agents.
    Use this key in the <code>Authorization: Bearer ...</code> header for <code>/api/*</code> endpoints.
  </p>

  {#if botApiKeyConfigured}
    <div class="mcp-status mcp-enabled">
      <div class="mcp-status-icon">
        <Icon name="check" size="md" />
      </div>
      <div class="mcp-status-info">
        <span class="mcp-status-label">Bot API access enabled</span>
        <span class="mcp-status-endpoint">Skill URL: <code>{mcpEndpointUrl}/SKILL.md</code></span>
      </div>
    </div>

    <div class="mcp-key-display">
      <label class="label" for="bot-api-key">Bot API Key</label>
      <div class="mcp-key-row">
        <input id="bot-api-key" type="password" class="input" value={botApiKey || '••••••••••••••••'} readonly />
        <button type="button" class="btn btn-secondary" on:click={copyBotKey} disabled={!botApiKey}>
          <Icon name="copy" size="sm" />
          Copy
        </button>
      </div>
      {#if !botApiKey}
        <p class="form-hint">Key is hidden after generation. Regenerate to copy again.</p>
      {/if}
    </div>

    <div class="mcp-actions">
      <button type="button" class="btn btn-secondary" on:click={generateBotKey} disabled={generatingBotKey}>
        <Icon name="refresh" size="sm" />
        Regenerate Key
      </button>
      <button type="button" class="btn btn-ghost btn-danger-text" on:click={openDeleteBotModal}>
        <Icon name="trash" size="sm" />
        Disable Bot API Access
      </button>
    </div>
  {:else}
    <div class="mcp-status mcp-disabled">
      <div class="mcp-status-icon">
        <Icon name="x" size="md" />
      </div>
      <div class="mcp-status-info">
        <span class="mcp-status-label">Bot API access disabled</span>
        <span class="mcp-status-hint">Generate a key to enable bearer token access for bots</span>
      </div>
    </div>

    <button type="button" class="btn btn-primary" on:click={generateBotKey} disabled={generatingBotKey}>
      <Icon name="plus" size="sm" />
      {generatingBotKey ? 'Generating...' : 'Generate Bot API Key'}
    </button>
  {/if}

  <div class="mcp-help mt-4">
    <details>
      <summary>How to use this key with bots</summary>
      <div class="mcp-help-content">
        <p>Reference the hosted skill file at:</p>
        <pre class="code-block">{`${mcpEndpointUrl}/SKILL.md`}</pre>
        <p class="mt-2">Example request:</p>
        <pre class="code-block">{`curl -H "Authorization: Bearer ${botApiKey || 'YOUR_BOT_API_KEY'}" \\
  "${mcpEndpointUrl}/api/invoices/paginated?page=1&per_page=10"`}</pre>
      </div>
    </details>
  </div>
</CollapsibleSection>

<style>
  .mcp-status {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-4);
  }

  .mcp-enabled {
    background: var(--color-success-light);
  }

  .mcp-disabled {
    background: var(--color-bg-sunken);
  }

  .mcp-status-icon {
    width: 40px;
    height: 40px;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .mcp-enabled .mcp-status-icon {
    background: var(--color-success);
    color: var(--color-text-inverse);
  }

  .mcp-disabled .mcp-status-icon {
    background: var(--color-border);
    color: var(--color-text-tertiary);
  }

  .mcp-status-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .mcp-status-label {
    font-weight: 600;
    color: var(--color-text);
  }

  .mcp-status-endpoint,
  .mcp-status-hint {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    word-break: break-all;
  }

  .mcp-status-endpoint code {
    background: var(--color-bg);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.875em;
    word-break: break-all;
  }

  .mcp-key-display {
    margin-bottom: var(--space-4);
  }

  .mcp-key-row {
    display: flex;
    gap: var(--space-2);
  }

  .mcp-key-row .input {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 0.8125rem;
  }

  .mcp-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }

  .mcp-help {
    border-top: 1px solid var(--color-border-light);
    padding-top: var(--space-4);
  }

  .mcp-help summary {
    font-weight: 500;
    cursor: pointer;
    color: var(--color-text-secondary);
    padding: var(--space-2) 0;
  }

  .mcp-help summary:hover {
    color: var(--color-text);
  }

  .mcp-help-content {
    margin-top: var(--space-3);
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  .mcp-help-content .code-block {
    background: var(--color-bg-sunken);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-3);
    margin: var(--space-2) 0;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    line-height: 1.5;
    white-space: pre;
  }

  .mcp-help-content ul {
    margin-top: var(--space-2);
    padding-left: var(--space-4);
  }

  .mcp-help-content li {
    margin-bottom: var(--space-1);
  }

  .mcp-help-content code {
    background: var(--color-bg-sunken);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 0.875em;
  }

  .btn-danger-text {
    color: var(--color-danger);
  }

  .btn-danger-text:hover:not(:disabled) {
    background: var(--color-danger-light);
  }
</style>
