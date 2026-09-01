<script lang="ts">
  import { onMount } from 'svelte';
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import Icon from '$lib/components/Icons.svelte';
  import SettingsApiKeyManager from './SettingsApiKeyManager.svelte';
  import { apiKeysApi } from '$lib/api';
  import { toast } from '$lib/stores';

  interface ApiKey {
    id: number;
    kind: string;
    label: string;
    prefix: string | null;
    created_at: string | null;
    last_used_at: string | null;
  }

  interface Props {
    mcpOpen?: boolean;
    botOpen?: boolean;
    appBaseUrl?: string;
    mcpEndpointUrl?: string;
  }

  let {
    mcpOpen = $bindable(false),
    botOpen = $bindable(false),
    appBaseUrl = $bindable(''),
    mcpEndpointUrl = ''
  }: Props = $props();

  let keys = $state<ApiKey[]>([]);
  let mcpRevealed = $state('');
  let botRevealed = $state('');

  const mcpKeys = $derived(keys.filter((key) => key.kind === 'mcp'));
  const botKeys = $derived(keys.filter((key) => key.kind === 'bot'));

  onMount(load);

  async function load() {
    try {
      keys = await apiKeysApi.list();
    } catch {
      toast.error('Failed to load API keys');
    }
  }
</script>

{#snippet statusPill(enabled: boolean, label: string, detail: string)}
  <div class="mcp-status {enabled ? 'mcp-enabled' : 'mcp-disabled'}">
    <div class="mcp-status-icon">
      <Icon name={enabled ? 'check' : 'x'} size="md" />
    </div>
    <div class="mcp-status-info">
      <span class="mcp-status-label">{label}</span>
      <span class="mcp-status-endpoint">{detail}</span>
    </div>
  </div>
{/snippet}

<CollapsibleSection title="MCP Integration" subtitle="Claude Desktop remote access" icon="settings" bind:open={mcpOpen}>
  <p class="form-hint mb-4">
    Enable remote access to Invoice Machine via Claude Desktop using the Model Context Protocol (MCP).
    Create a key for each machine you connect from; revoke them one at a time.
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

  {@render statusPill(
    mcpKeys.length > 0,
    mcpKeys.length > 0 ? 'Remote access enabled' : 'Remote access disabled',
    mcpKeys.length > 0 ? `Endpoint: ${mcpEndpointUrl}/mcp` : 'Create an API key to enable Claude Desktop connections'
  )}

  <SettingsApiKeyManager
    kind="mcp"
    keys={mcpKeys}
    placeholder="Key name (e.g. Laptop)"
    bind:revealedKey={mcpRevealed}
    onchanged={load}
  />

  <div class="mcp-help mt-4">
    <details>
      <summary>How to configure Claude Desktop</summary>
      <div class="mcp-help-content">
        <p>Add this to your Claude Desktop config file (requires Node.js for <code>mcp-remote</code>):</p>
        <pre class="code-block">{`{
  "mcpServers": {
    "invoice-machine": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "${mcpEndpointUrl}/mcp",
        "--header",
        "Authorization: Bearer ${mcpRevealed || 'YOUR_API_KEY'}"
      ]
    }
  }
}`}</pre>
        <p class="mt-2">Clients that support remote MCP servers directly (e.g. claude.ai custom connectors) can use the endpoint URL <code>{mcpEndpointUrl}/mcp</code> with the same Bearer token instead.</p>
        <p class="mt-2"><strong>Config file location:</strong></p>
        <ul>
          <li><strong>macOS:</strong> <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></li>
          <li><strong>Windows:</strong> <code>%APPDATA%\Claude\claude_desktop_config.json</code></li>
        </ul>
        <p class="mt-2">
          Speaks MCP spec <strong>2026-07-28</strong> and every earlier revision on the
          same endpoint, so any client version connects without extra configuration.
          The older <code>/mcp/sse</code> endpoint still works but is deprecated.
        </p>
        <p class="mt-2">
          Actions that cannot be undone — emailing an invoice, triggering a
          schedule early — ask for confirmation before they run, naming the
          recipient or schedule. See the Help page for the full breakdown.
        </p>
      </div>
    </details>
  </div>
</CollapsibleSection>

<CollapsibleSection title="Bot API Key" subtitle="REST API automation access" icon="settings" bind:open={botOpen}>
  <p class="form-hint mb-4">
    Create keys for conventional REST API access with bots and agents.
    Use a key in the <code>Authorization: Bearer ...</code> header for <code>/api/*</code> endpoints.
  </p>

  {@render statusPill(
    botKeys.length > 0,
    botKeys.length > 0 ? 'Bot API access enabled' : 'Bot API access disabled',
    botKeys.length > 0 ? `Skill URL: ${mcpEndpointUrl}/SKILL.md` : 'Create a key to enable bearer token access for bots'
  )}

  <SettingsApiKeyManager
    kind="bot"
    keys={botKeys}
    placeholder="Key name (e.g. CI runner)"
    bind:revealedKey={botRevealed}
    onchanged={load}
  />

  <div class="mcp-help mt-4">
    <details>
      <summary>How to use this key with bots</summary>
      <div class="mcp-help-content">
        <p>Reference the hosted skill file at:</p>
        <pre class="code-block">{`${mcpEndpointUrl}/SKILL.md`}</pre>
        <p class="mt-2">Example request:</p>
        <pre class="code-block">{`curl -H "Authorization: Bearer ${botRevealed || 'YOUR_API_KEY'}" \\
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

  .mcp-status-endpoint {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    word-break: break-all;
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
</style>
