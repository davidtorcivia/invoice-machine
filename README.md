# Invoice Machine

Self-hosted invoicing for freelancers and small businesses. Write invoices and quotes, track what you are owed, get paid, and let an AI assistant do the typing.

Everything runs on a single SQLite file and a single container. No SaaS account, no subscription. SMTP, Stripe, and S3 stay optional and only talk to hosts you configure.

## Features

**Billing**
- Invoices and quotes with automatic daily numbering
- Quote to invoice conversion that keeps the original quote as a record
- Payment tracking with partial payments, running balances, and A/R aging
- Hosted card payment links via Stripe, with a signed webhook that reconciles automatically
- Recurring schedules for retainers and subscriptions
- Tax with per-invoice, per-client, and global defaults
- Multi-currency, with per-currency totals and an optional converted roll-up

**Getting paid**
- SMTP delivery of invoice PDFs
- Automated payment reminders on a schedule you choose
- Overdue detection and status updates

**Everything else**
- Branded PDF generation with your logo and accent color
- Client database with addresses, terms, and per-client defaults
- Full-text search across invoices, clients, and line items
- CSV export of invoices, line items, payments, and clients
- Revenue analytics and client lifetime value
- Automatic daily backups with optional S3 upload
- MCP server for Claude, plus a separate bot API key for scripts
- Dark mode, keyboard-friendly tables, and offline-capable assets

## Quick Start

```bash
git clone https://github.com/davidtorcivia/invoice-machine.git
cd invoice-machine
docker-compose up -d
```

Open http://localhost:8080 and create your admin account.

Then:

1. Go to Settings and fill in your business name, address, and logo
2. Add payment instructions (bank details, Venmo, whatever you use)
3. Start writing invoices

## Configuration

Set these in a `.env` file or as environment variables. See `.env.example` for a full template.

### Core

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | External port mapping | `8080` |
| `DATA_DIR` | Directory for data storage | `./data` |
| `APP_BASE_URL` | Public base URL of the app | `http://localhost:8080` |
| `ENVIRONMENT` | `development`, `staging`, or `production` | `development` |
| `TRASH_RETENTION_DAYS` | Days before trashed items are purged | `90` |

### Security

| Variable | Description | Default |
|----------|-------------|---------|
| `INVOICE_MACHINE_ENCRYPTION_KEY` | Encrypts stored credentials. Required in production. | none |
| `SECURE_COOKIES` | Enable secure cookies (requires HTTPS) | `false` |
| `TRUST_PROXY_HEADERS` | Trust `CF-Connecting-IP` / `X-Forwarded-For` | `false` |
| `SENTRY_DSN` | Report unhandled errors to Sentry (no PII) | none |
| `CORS_ORIGINS` | Allowed origins, comma-separated | `http://localhost:3000,http://localhost:8080` |

### Invoice defaults

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_PAYMENT_TERMS_DAYS` | Default payment terms | `30` |
| `DEFAULT_CURRENCY_CODE` | Default currency | `USD` |
| `DEFAULT_ACCENT_COLOR` | PDF accent color (hex) | `#16a34a` |

### Production

Behind HTTPS (Cloudflare Tunnel, nginx, Caddy), all of these are required:

```env
INVOICE_MACHINE_ENCRYPTION_KEY=your_64_character_hex_key_here
APP_BASE_URL=https://invoices.yourdomain.com
ENVIRONMENT=production
SECURE_COOKIES=true
TRUST_PROXY_HEADERS=true
CORS_ORIGINS=https://invoices.yourdomain.com

# Recommended: keep data outside the container
DATA_DIR=/var/lib/invoice-machine/data
```

`CORS_ORIGINS` must include `APP_BASE_URL`. The app logs a warning at startup if it does not.

### Generating an encryption key

This key encrypts your SMTP password, Stripe credentials, and S3 keys. In production the app refuses to start without it.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
```

Store it somewhere safe and keep it out of version control. Back it up separately from your database: without the key, stored credentials cannot be decrypted and have to be entered again.

## Usage

### Invoices and quotes

Create an invoice from Invoices > New Invoice, pick a client, add line items with quantities or hours, and set the dates. Quotes work the same way with the quote checkbox ticked.

Numbers follow `YYYYMMDD-N`, where N restarts each day. Quotes use a `Q-` prefix. Changing the date of an auto-numbered document renumbers it; a number you typed yourself is never overwritten.

When a client accepts a quote, use **Convert to invoice**. That creates a new invoice carrying the quote's line items, tax, and currency, and links the two together. The quote stays exactly as the client saw it.

### Payments

Record payments against an invoice from its detail page. Partial payments are fully supported: the invoice keeps a running balance, and it flips to paid on its own once payments cover the total. Delete a payment and it reverts to sent or overdue as appropriate.

The Reports page shows an accounts receivable aging table, bucketing outstanding balances by how far past due they are. Amounts in different currencies are always reported separately.

### Online payments

Settings > Online payments connects a Stripe account so clients can pay by card.

1. Create a [restricted API key](https://docs.stripe.com/keys/restricted-api-keys) in Stripe with write access to Checkout Sessions, and paste it in. A restricted key is strongly preferred over a full secret key, so a leaked value cannot move money or read your customer list.
2. Add a webhook in Stripe pointing at `https://your-server.com/api/webhooks/stripe`, subscribed to `checkout.session.completed`.
3. Paste the webhook signing secret back into Settings.

Each invoice then gets a **Create payment link** button. The link covers the outstanding balance, appears on the PDF and in emails via the `{payment_link}` placeholder, and completed payments are recorded automatically. Webhook requests are rejected unless they carry a valid Stripe signature within a five-minute window, and each Stripe event is recorded at most once.

Which card and wallet types appear at checkout is controlled from your Stripe dashboard.

### Recurring invoices

Recurring > New Schedule sets up retainers and subscriptions. Choose a client, a frequency (daily, weekly, monthly, quarterly, yearly), and when in the period to bill: a day of the month, a day of the week, which month of the quarter, or which month of the year.

Schedules can carry their own line items, tax, notes, and payment instructions, and can email each generated invoice automatically. Generation runs daily at 02:00 UTC and catches up on any periods missed while the app was down, dating each invoice to its own period. You can also trigger, pause, and resume a schedule by hand.

### Email

Settings > Email configures SMTP. Any provider works (Gmail, Fastmail, SendGrid, Mailgun, Postmark). Test the connection, then use **Send email** on any invoice to deliver the PDF.

Subject and body templates live in Settings > Email templates and accept placeholders including `{invoice_number}`, `{client_name}`, `{total}`, `{amount_due}`, `{due_date}`, `{line_items}`, and `{payment_link}`.

### Payment reminders

Settings > Payment reminders chases unpaid invoices for you. Pick a schedule as day offsets around the due date, for example three days before, then one, seven, and fourteen days after. The sweep runs daily at 09:00 UTC.

Each offset is sent at most once per invoice. Fully paid invoices are never chased, partially paid ones are chased for the balance, and turning reminders on for an already-overdue invoice sends a single current reminder rather than the whole backlog.

### Multi-currency

Invoices carry their own currency, and totals are reported per currency throughout the app. Money in different currencies is never added together.

For a single headline number, add exchange rates in Settings > Exchange rates. A rate is copied onto each invoice when it is issued, so historical invoices keep the rate that applied at the time, and the Reports page gains a converted roll-up. Invoices with no recorded rate are excluded from that roll-up and reported as such, so a partial picture is never presented as a complete one.

### Export

Reports > Export downloads CSVs of invoices, line items, payments, or clients for the selected year. Money is written as plain decimals alongside an explicit currency column, which is what spreadsheets and accounting imports expect.

### PDFs

Click Download PDF on any invoice. PDFs regenerate when the invoice actually changes and are served from disk otherwise. The download is named `[Client Name] - [Invoice Number].pdf`.

### Search

The sidebar search covers invoice numbers, client names, notes, and line item descriptions, ranked by relevance with partial matching.

## MCP Integration

Invoice Machine ships an MCP server, so Claude can create invoices, record payments, chase clients, and pull analytics for you.

### Setup

Generate a key under Settings > MCP Integration, then add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "invoice-machine": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-server.com/mcp",
        "--header",
        "Authorization: Bearer YOUR_MCP_API_KEY"
      ]
    }
  }
}
```

The endpoint runs on the same port as the web app and works behind any reverse proxy. `/mcp` uses the stateless Streamable HTTP transport, so connections survive proxy idle timeouts and app restarts. Clients with native remote MCP support can point at the URL directly with the same bearer token and skip `mcp-remote`. The legacy SSE transport stays available at `/mcp/sse`.

### Protocol version

The server implements MCP spec **2026-07-28** and still answers every earlier
revision from the same endpoint, so old and new clients both work without
configuration:

| Client speaks | What happens |
| --- | --- |
| 2026-07-28 | No handshake. Each request carries its own protocol version and identity, so any request can hit any instance. |
| 2025-11-25 and earlier | The `initialize` handshake, exactly as before. |

`GET /mcp/status` reports the version the server prefers and the full list it
accepts.

Two things the 2026-07-28 revision changes that are worth knowing:

- **`tools/list` is cacheable.** The server advertises a 5-minute TTL
  (`ttlMs`), so clients stop re-fetching the tool list on every reconnect. The
  list only changes when the app restarts.
- **Sessions are gone.** There is no `Mcp-Session-Id` and no server-side state
  between calls, which is what makes the endpoint safe to run behind a proxy
  that drops idle connections.

### Safety: what a client knows before it calls

Every tool is annotated so a client can tell a lookup from something that moves
money, and auto-approve accordingly:

| Hint | Meaning | Examples |
| --- | --- | --- |
| `readOnlyHint` | Changes nothing | `list_invoices`, `get_revenue_summary` |
| `destructiveHint` | Removes or reverses data | `delete_invoice`, `delete_payment` |
| `idempotentHint` | Safe to retry | `update_client`, `generate_pdf`, `record_payment` |
| `openWorldHint` | Reaches outside the app | `send_invoice_email`, `test_smtp_connection` |

`record_payment` requires an `idempotency_key`. Replaying the same key returns
the payment already recorded rather than adding a second one, so a retried call
cannot double-record — the case that used to slip through was a repeated
*partial* payment, since a repeated full one was already refused for exceeding
the balance. Over REST, `POST /api/invoices/{id}/payments` accepts the same
thing as an optional `Idempotency-Key` header (optional there because it is the
browser path).

Two tools additionally **ask before acting**, because their effects cannot be
undone: `send_invoice_email` and `trigger_recurring_schedule`. The prompt names
the actual recipient or schedule. Declining stops the call. Clients that do not
support elicitation are not blocked — they proceed as before and rely on the
annotations above for their own approval flow.

### Resources

Read-only data is addressable directly, without spending a tool call:

| URI | Contents |
| --- | --- |
| `invoice://{invoice_number}` | One invoice or quote with line items, e.g. `invoice://20250115-1` |
| `client://{client_id}` | One client's details and terms |
| `invoices://outstanding` | Everything still owed, due date first |
| `profile://business` | Your own business details (never secrets) |

Invoices are addressed by the number printed on the document, not the database
ID.

### Prompts

Three starting points appear in clients that show a prompt picker:

- **Draft an invoice** — matches the client's previous rates and wording
- **Chase overdue invoices** — triages what is owed and drafts chase emails
- **Month-end summary** — revenue, outstanding balances, and top clients

All three stop short of sending anything; they draft and report, and leave the
send to you.

Running locally with Docker, you can use stdio instead:

```json
{
  "mcpServers": {
    "invoice-machine": {
      "command": "docker",
      "args": ["exec", "-i", "invoice-machine", "python", "-m", "invoice_machine.mcp.server"]
    }
  }
}
```

### Things to ask for

- "Create an invoice for Acme Corp, 40 hours of website development at $150/hour"
- "Acme paid $2,000 against invoice 20250115-1, record it"
- "Show me the aging report, who is more than 60 days late?"
- "Convert quote Q-20250110-1 to an invoice"
- "Set up a monthly retainer for Acme, $2,000 on the 1st"
- "Export this year's payments as CSV"
- "What is my revenue for 2024 across all currencies?"

### Available tools

| Area | Tools |
|------|-------|
| Clients | `list_clients`, `get_client`, `create_client`, `update_client`, `delete_client`, `restore_client` |
| Invoices | `list_invoices`, `get_invoice`, `create_invoice`, `update_invoice`, `delete_invoice`, `restore_invoice`, `convert_quote_to_invoice` |
| Line items | `add_invoice_item`, `update_invoice_item`, `remove_invoice_item` |
| Payments | `list_payments`, `record_payment`, `delete_payment`, `get_aging_report` |
| Recurring | `list_recurring_schedules`, `get_recurring_schedule`, `create_recurring_schedule`, `update_recurring_schedule`, `delete_recurring_schedule`, `pause_recurring_schedule`, `resume_recurring_schedule`, `trigger_recurring_schedule` |
| Analytics | `get_revenue_summary`, `get_consolidated_summary`, `get_client_lifetime_value`, `get_client_invoice_context` |
| Email | `send_invoice_email`, `preview_invoice_email`, `get_email_templates`, `update_email_templates`, `test_smtp_connection` |
| Business profile | `get_business_profile`, `update_business_profile`, `add_payment_method`, `remove_payment_method` |
| Other | `search`, `export_csv`, `generate_pdf`, `list_trash` |

### Key scope

MCP keys only authenticate `/mcp/*` connections. For ordinary REST calls, use a bot API key instead.

Create as many keys as you need under Settings > MCP Integration. Each one is labeled, shown once, and can be rotated or revoked on its own without touching the others.

## Bot API

For scripts, automations, and agents making plain HTTP requests. Create a labeled key under Settings > Bot API Key (it is shown once, and is revocable on its own) and send it as a bearer token:

```bash
curl -H "Authorization: Bearer YOUR_BOT_API_KEY" \
  "https://your-server.com/api/invoices/paginated?page=1&per_page=10"
```

A hosted skill file describing the API lives at `https://your-server.com/SKILL.md`.

## Backups

Automatic backups run daily at midnight UTC once enabled under Settings > Backup & Restore. Set a retention period (30 days by default) and optionally upload to any S3-compatible store (AWS S3, Backblaze B2, Cloudflare R2, MinIO).

Backups are taken through SQLite's online backup API, so they are consistent even while the app is writing. Restoring creates a pre-restore safety copy first, then applies any pending schema migrations, so a backup from an older release comes back usable.

The `data/` directory holds everything: database, PDFs, logos, and backups. Copying it is a complete backup.

## Security

**Authentication.** PBKDF2-HMAC-SHA256 with 600,000 iterations, password complexity requirements, login rate limiting, database-backed sessions with 30-day expiry, and CSRF protection via double-submit cookies.

**Credentials at rest.** SMTP passwords, Stripe keys, and S3 credentials are encrypted with Fernet. Plaintext credentials are rejected outright in production.

**Webhooks.** Stripe requests are verified by HMAC signature with a replay window before anything in the payload is trusted.

**Input handling.** Path traversal guards on every file operation, email header injection protection, magic-byte validation on image uploads, parameterized queries throughout, FTS5 query sanitization, and an SSRF guard on outbound SMTP connections.

**Container.** Runs as a non-root user with production-only dependencies. The UI ships its own fonts and assets, so no browsing data leaks to a CDN and the app works offline.

### Production checklist

1. Generate and set `INVOICE_MACHINE_ENCRYPTION_KEY`, `chmod 600` your `.env`, and back the key up somewhere separate
2. Set `SECURE_COOKIES=true` behind HTTPS
3. Set `TRUST_PROXY_HEADERS=true` only if a reverse proxy overwrites client IP headers
4. Point `CORS_ORIGINS` at your domain only
5. Turn on automatic backups with S3 for offsite copies
6. Put an access layer in front of it (Cloudflare Access, Tailscale, or a VPN)
7. Use a Stripe restricted key rather than a secret key
8. Pull new images regularly

## Observability

Every request gets an id, returned as `X-Request-ID` (a caller-supplied one is
echoed when it is short and log-safe) and stamped on every log line for that
request as `[id]`. Background jobs log under a `job-` id. The app writes one
access line per request, so run uvicorn with `--no-access-log` as the Docker
image does.

`GET /health` (unauthenticated) reports `status` and whether this process holds
the scheduler (`active`) or is standing by. `GET /api/system/status`
(authenticated) adds version, environment, uptime, and for every background job
its run and failure counts, last start, last success, last error, and duration.

Set `SENTRY_DSN` to report unhandled exceptions to Sentry. Events are tagged
with the request id; request bodies, local variables, and personal data are
never sent. An unhandled error returns a 500 whose body carries the request id.

## Deployment

### Docker Compose

```yaml
services:
  invoice-machine:
    image: invoice-machine:latest
    container_name: invoice-machine
    ports:
      - "8080:8080"
    environment:
      - INVOICE_MACHINE_ENCRYPTION_KEY=${INVOICE_MACHINE_ENCRYPTION_KEY}
      - APP_BASE_URL=https://invoices.yourdomain.com
      - ENVIRONMENT=production
      - SECURE_COOKIES=true
      - TRUST_PROXY_HEADERS=true
      - CORS_ORIGINS=https://invoices.yourdomain.com
      - DATABASE_URL=sqlite+aiosqlite:////app/data/invoice_machine.db
      - DATA_DIR=/app/data
    volumes:
      - /var/lib/invoice-machine/data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
      interval: 30s
      timeout: 3s
      retries: 3
```

Two things that catch people out: `DATABASE_URL` needs four slashes (three for the SQLite URL plus the leading slash of the absolute path), and the volume mount is what persists your database, PDFs, logos, and backups. Keep `container_name` as `invoice-machine` if you plan to use MCP over `docker exec`.

### Cloudflare Tunnel

```bash
cloudflared tunnel create invoice-machine
```

Configure an Access policy in the Cloudflare dashboard, then set `APP_BASE_URL`, `SECURE_COOKIES=true`, and `TRUST_PROXY_HEADERS=true`. The app then reads `CF-Connecting-IP` for rate limiting and audit logging, so limits apply per client rather than to the tunnel as a whole.

### Scheduled jobs

One worker holds a lock and runs these; the times are UTC.

| Job | When |
|-----|------|
| Database backup | 00:00 |
| Overdue invoice sweep | 01:00 |
| Recurring invoice generation | 02:00 |
| Trash purge | 03:00 |
| Payment reminders | 09:00 |
| Expired session cleanup | hourly |

## Development

```bash
# Backend
uv sync --extra dev && source .venv/bin/activate   # or: pip install -e ".[dev]"
uvicorn invoice_machine.main:app --reload --port 8080

# Frontend
cd frontend && npm install && npm run dev

# Tests
pytest -q
ruff check invoice_machine/ tests/
```

Schema changes go through Alembic, which is the single source of truth for the database:

```bash
alembic revision -m "describe the change"
alembic upgrade head
```

`tests/test_schema_drift.py` runs the migrations against a throwaway database and fails if the models and migrations disagree.

### Layout

```
invoice_machine/
├── api/          FastAPI routes
├── service/      Business logic (invoices, payments, recurring, analytics, export, reminders, stripe, backups, search)
├── mcp/          MCP tool definitions
├── pdf/          WeasyPrint templates and generation
├── alembic/      Database migrations
├── database.py   SQLAlchemy models
└── main.py       App entry point

frontend/         SvelteKit UI
tests/            Test suite
data/             Runtime data, gitignored (database, pdfs, logos, backups)
```

## License

MIT. See [LICENSE](LICENSE).
