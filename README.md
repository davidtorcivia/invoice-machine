# Invoice Machine

A self-hosted invoicing application for freelancers and small businesses. Create invoices and quotes, manage clients, and generate PDFs.

## Features

- Create and track invoices and quotes with automatic numbering
- Client database with address and payment terms
- PDF generation with customizable branding and logo
- **Tax support** with per-invoice, per-client, or global defaults
- **Recurring invoices** for retainers and subscriptions
- **SMTP email** to send invoices directly to clients
- **Full-text search** across invoices and clients
- Built-in authentication with rate limiting
- Automatic daily backups with optional S3 storage
- Dark mode with system preference detection
- Overdue invoice highlighting and automatic status updates
- **Analytics** for revenue tracking and client insights
- MCP integration for Claude Desktop (separate key from REST bot API)
- Bot API key for conventional `/api/*` automation with hosted `SKILL.md`
- SQLite storage, runs anywhere

## Quick Start

### Docker

```bash
git clone https://github.com/davidtorcivia/invoice-machine.git
cd invoice-machine
docker-compose up -d
```

Open http://localhost:8080 and create your admin account.

### Production Deployment

For production, set environment variables to configure the port and data directory:

```bash
# Set your production values
export PORT=8085
export DATA_DIR=/nvme-mirror/apps/invoice-machine/data
export APP_BASE_URL=https://invoices.yourdomain.com

# Start the container
docker-compose up -d
```

Or create a `.env` file in the project directory:

```env
PORT=8085
DATA_DIR=/nvme-mirror/apps/invoice-machine/data
APP_BASE_URL=https://invoices.yourdomain.com
```

The container always listens on port 8080 internally. The `PORT` variable maps it to your desired external port.

### First Run

1. Create your admin account on the setup screen
2. Go to Settings to configure your business name, address, and logo
3. Add payment instructions (bank details, Venmo, etc.)
4. Start creating invoices

## Configuration

Set these in a `.env` file or as environment variables. See `.env.example` for a complete template.

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | External port mapping | `8080` |
| `DATA_DIR` | Directory for data storage | `./data` |
| `APP_BASE_URL` | Base URL for the application | `http://localhost:8080` |
| `ENVIRONMENT` | Environment mode (development/staging/production) | `development` |
| `TRASH_RETENTION_DAYS` | Days before auto-purge from trash | `90` |

### Security Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `INVOICE_MACHINE_ENCRYPTION_KEY` | Encryption key for sensitive data (SMTP passwords) | Required in production |
| `SECURE_COOKIES` | Enable secure cookies (requires HTTPS) | `false` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `http://localhost:3000,http://localhost:8080` |

#### Generating an Encryption Key

The encryption key protects sensitive data like SMTP credentials. In production, this key is **required**—the application will refuse to start without it.

Generate a secure 32-byte (64 hex characters) key using any of these methods:

**Python:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**OpenSSL:**
```bash
openssl rand -hex 32
```

**PowerShell:**
```powershell
-join ((1..32) | ForEach-Object { "{0:x2}" -f (Get-Random -Maximum 256) })
```

Store the key securely and **never commit it to version control**. If you lose the key, any encrypted credentials (SMTP passwords) will become unreadable and must be re-entered.

### Invoice Defaults

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_PAYMENT_TERMS_DAYS` | Default payment terms | `30` |
| `DEFAULT_CURRENCY_CODE` | Default currency | `USD` |
| `DEFAULT_ACCENT_COLOR` | PDF accent color (hex) | `#16a34a` |

### Production Configuration

For production deployments behind HTTPS (Cloudflare Tunnel, nginx, etc.), these settings are **required**:

```env
# Required for production
INVOICE_MACHINE_ENCRYPTION_KEY=your_64_character_hex_key_here
APP_BASE_URL=https://invoices.yourdomain.com
ENVIRONMENT=production
SECURE_COOKIES=true
CORS_ORIGINS=https://invoices.yourdomain.com

# Recommended: persistent data storage
DATA_DIR=/var/lib/invoice-machine/data
```

| Variable | Required | Description |
|----------|----------|-------------|
| `INVOICE_MACHINE_ENCRYPTION_KEY` | **Yes** | Encryption key for sensitive data (see [Generating an Encryption Key](#generating-an-encryption-key)) |
| `APP_BASE_URL` | **Yes** | Must match your public URL for PDF links, MCP, and hosted `SKILL.md` |
| `ENVIRONMENT` | **Yes** | Set to `production` for proper logging and defaults |
| `SECURE_COOKIES` | **Yes** | Must be `true` when using HTTPS |
| `CORS_ORIGINS` | **Yes** | Must match your domain to prevent CORS errors |
| `DATA_DIR` | Recommended | Persistent storage location outside container |

## Usage

### Invoices

1. Go to Invoices > New Invoice
2. Select a client or enter details manually
3. Add line items with descriptions, quantities or hours, and prices
4. Set issue date and due date
5. Click Create Invoice

### Quotes

Same as invoices, but check "This is a Quote". Quotes are numbered separately with a Q- prefix.

### PDF Generation

Click Download PDF on any invoice. PDFs regenerate automatically when the invoice changes. Filename format: `[Client Name] - [Invoice Number].pdf`

### Invoice Numbers

Format: `YYYYMMDD-N` where N resets daily.

- First invoice on June 23, 2025: `20250623-1`
- Second invoice same day: `20250623-2`
- Quotes: `Q-YYYYMMDD-N`

Changing an invoice's date regenerates its number.

### Tax Handling

Invoice Machine supports optional tax with a cascade system:

1. **Invoice-level**: Override tax settings on individual invoices
2. **Client-level**: Set default tax for specific clients
3. **Global default**: Configure in Settings > Tax Settings

The cascade priority is: Invoice > Client > Global. Tax is disabled by default.

To enable tax:
1. Go to Settings and enable tax with your default rate
2. Optionally set per-client rates in the client editor
3. Override on specific invoices as needed

### Recurring Invoices

Set up recurring invoices for retainers, subscriptions, or regular services:

1. Go to Clients > Select a client > Recurring Schedules
2. Create a schedule with:
   - Name (e.g., "Monthly Retainer")
   - Frequency (daily, weekly, monthly, quarterly, yearly)
   - Schedule day (1-31 for monthly, 0-6 for weekly)
   - Line items and amounts
3. Invoices are generated automatically at 2 AM UTC

You can also trigger schedules manually or pause/resume them.

### Email Delivery

Send invoices directly to clients via SMTP:

1. Go to Settings > Email Configuration
2. Configure your SMTP server:
   - Host and port (587 for TLS, 465 for SSL)
   - Username and password
   - From name and email
3. Click "Test Connection" to verify
4. On any invoice, click "Send Email" to deliver the PDF

Works with any SMTP provider (Gmail, SendGrid, Mailgun, etc.).

### Search

Use the search bar to find invoices and clients:
- Search by invoice number, client name, or notes
- Results are ranked by relevance using full-text search
- Partial matches are supported

## MCP Integration

Invoice Machine works with Claude Desktop through MCP. You can create invoices, manage clients, and generate PDFs through natural language.

### Setup

1. Go to Settings > MCP Integration
2. Click Generate API Key
3. Copy the configuration to your Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "invoice-machine": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-server.com/mcp/sse",
        "--header",
        "Authorization: Bearer YOUR_MCP_API_KEY"
      ]
    }
  }
}
```

Replace `your-server.com` with your actual domain and `YOUR_MCP_API_KEY` with the key from Settings.

The MCP endpoint runs on the same port as the web app. Works with Cloudflare Tunnel or any reverse proxy.

### Key Scope

The MCP API key is only for MCP (`/mcp/*`) connections from Claude Desktop.
For conventional REST API calls (`/api/*`), use the separate Bot API key described below.

## Bot API Integration

Use a dedicated Bot API key for automation tools, scripts, and agents making standard HTTP requests.

### Setup

1. Go to Settings > Bot API Key
2. Click Generate Bot API Key
3. Save the key immediately (it is only shown once)
4. Send it as a bearer token in REST API requests

### Authentication

Use this header on `/api/*` requests:

```http
Authorization: Bearer YOUR_BOT_API_KEY
```

### Skill File

Invoice Machine exposes a hosted skill file for agent setup at:

```text
https://your-server.com/SKILL.md
```

### Example Request

```bash
curl -H "Authorization: Bearer YOUR_BOT_API_KEY" \
  "https://your-server.com/api/invoices/paginated?page=1&per_page=10"
```

### Local Docker Setup

If running locally with Docker, you can use stdio transport instead:

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

### Example Commands

**Invoices:**
- "Create an invoice for Acme Corp for website development, 40 hours at $150/hour"
- "Create a quote for logo design $500, brand guidelines $1200"
- "List all unpaid invoices from last month"
- "Mark invoice 20250115-1 as paid"
- "Generate PDF for all draft invoices"

**Recurring:**
- "Set up a monthly retainer for Acme Corp, $2000 on the 1st of each month"
- "Pause the recurring schedule for Client X"
- "Trigger the quarterly invoice for Big Corp now"

**Analytics:**
- "What's my revenue summary for 2024?"
- "Who are my top 5 clients by total paid?"
- "Show lifetime value for Acme Corp"

**Email:**
- "Send invoice 20250115-1 to john@acme.com"
- "Email the latest invoice to the client"

**Search:**
- "Search for invoices containing 'website'"
- "Find all clients named Smith"

### MCP Tools

**Business Profile:** `get_business_profile`, `update_business_profile`, `add_payment_method`, `remove_payment_method`

**Clients:** `list_clients`, `get_client`, `create_client`, `update_client`, `delete_client`, `restore_client`

**Invoices:** `list_invoices`, `get_invoice`, `create_invoice`, `update_invoice`, `delete_invoice`, `restore_invoice`

**Line Items:** `add_invoice_item`, `update_invoice_item`, `remove_invoice_item`

**Recurring:** `list_recurring_schedules`, `get_recurring_schedule`, `create_recurring_schedule`, `update_recurring_schedule`, `delete_recurring_schedule`, `pause_recurring_schedule`, `resume_recurring_schedule`, `trigger_recurring_schedule`

**Search:** `search` - Full-text search across invoices and clients

**Analytics:** `get_revenue_summary`, `get_top_clients`, `get_client_lifetime_value`

**Email:** `send_invoice_email`, `test_smtp_connection`

**Other:** `generate_pdf`, `list_trash`

## Project Structure

```
invoice-machine/
├── invoice_machine/     # Python backend
│   ├── api/             # FastAPI routes
│   ├── mcp/             # MCP server
│   ├── pdf/             # PDF generation
│   ├── alembic/         # Database migrations
│   ├── database.py      # SQLAlchemy models
│   ├── services.py      # Business logic
│   ├── email.py         # SMTP email service
│   ├── config.py        # Configuration management
│   └── main.py          # FastAPI app
├── frontend/            # SvelteKit frontend
├── tests/               # Test suite
│   ├── test_services.py # Service tests
│   ├── test_api.py      # API tests
│   ├── test_new_features.py  # Feature tests
│   └── test_security.py # Security tests
├── data/                # Runtime data (gitignored)
│   ├── invoice_machine.db  # SQLite database
│   ├── backups/         # Database backups
│   ├── pdfs/            # Generated PDFs
│   └── logos/           # Uploaded logos
├── alembic.ini          # Alembic configuration
├── .env.example         # Environment template
└── docker-compose.yml
```

## Development

### Backend

```bash
pip install -e ".[dev]"
python -c "import mcp; print('mcp installed')"
uvicorn invoice_machine.main:app --reload --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev
npm run build  # Production build
```

### Tests

```bash
pytest tests/ -v
```

## Backup

### Automatic Backups

Invoice Machine can automatically back up your database daily at midnight UTC.

1. Go to Settings > Backup & Restore
2. Enable "Automatic daily backups"
3. Set retention period (default: 30 days)

### S3 Storage

Optionally upload backups to S3-compatible storage (AWS S3, Backblaze B2, MinIO):

1. Enable "Upload backups to S3-compatible storage"
2. Enter your endpoint URL, credentials, bucket, and region
3. Click "Test S3 Connection" to verify

### Manual Backup

All data lives in the `data/` directory. Copy it to back up everything. You can also create manual backups from the Settings page and download them directly.

### Restore

Click the restore button on any backup to restore. A pre-restore backup is created automatically. The application needs to be restarted after restore.

## Security

Invoice Machine includes several security features:

### Authentication
- PBKDF2-HMAC-SHA256 password hashing with 600,000 iterations
- Password complexity requirements (minimum 8 characters with lowercase, uppercase, and digit)
- Rate limiting on login endpoints (3 attempts/minute)
- Database-backed sessions with 30-day expiration
- CSRF protection using double-submit cookie pattern
- Configurable secure cookies for HTTPS deployments

### Credential Encryption
- SMTP passwords and other sensitive data encrypted at rest using Fernet (AES-128-CBC)
- Encryption key required in production (application refuses to start without it)
- Key derivation uses PBKDF2-HMAC-SHA256 with unique salt

### Input Validation
- Path traversal prevention on file operations
- Email header injection protection
- Image upload validation (magic bytes + extension)
- SQL injection prevention via SQLAlchemy ORM
- FTS5 query sanitization

### Container Security
- Docker container runs as non-root user (UID 1000)
- Minimal attack surface with production-only dependencies

### Production Recommendations

1. **Set encryption key**: Generate and set `INVOICE_MACHINE_ENCRYPTION_KEY` (see [Generating an Encryption Key](#generating-an-encryption-key))
2. **Use HTTPS**: Set `SECURE_COOKIES=true` when behind HTTPS
3. **Restrict CORS**: Set `CORS_ORIGINS` to your actual domain only
4. **Regular backups**: Enable automatic backups with S3 for offsite storage
5. **Access control**: Use Cloudflare Access or similar for additional protection
6. **Keep updated**: Pull latest Docker images regularly

## Deployment

For remote access, use a reverse proxy. Example with Cloudflare Tunnel:

1. `cloudflared tunnel create invoice-machine`
2. Configure Access policy in Cloudflare dashboard
3. Set `APP_BASE_URL` in `.env`
4. Set `SECURE_COOKIES=true` for HTTPS

### Docker Compose Production Example

```yaml
version: '3.8'
services:
  invoice-machine:
    image: invoice-machine:latest
    container_name: invoice-machine
    ports:
      - "8080:8080"
    environment:
      # Required for production
      - INVOICE_MACHINE_ENCRYPTION_KEY=${INVOICE_MACHINE_ENCRYPTION_KEY}
      - APP_BASE_URL=https://invoices.yourdomain.com
      - ENVIRONMENT=production
      - SECURE_COOKIES=true
      - CORS_ORIGINS=https://invoices.yourdomain.com
      # Database (uses container path)
      - DATABASE_URL=sqlite+aiosqlite:////app/data/invoice_machine.db
      - DATA_DIR=/app/data
      # Optional: customize defaults
      - DEFAULT_PAYMENT_TERMS_DAYS=30
      - DEFAULT_CURRENCY_CODE=USD
      - TRASH_RETENTION_DAYS=90
    volumes:
      - /var/lib/invoice-machine/data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
      interval: 30s
      timeout: 3s
      retries: 3
```

**Important notes:**
- The `DATABASE_URL` uses 4 slashes (`////app/data/`) because SQLite URLs need 3 slashes plus the absolute path
- The volume mount (`/var/lib/invoice-machine/data:/app/data`) persists all data including the database, PDFs, logos, and backups
- Set `container_name` to `invoice-machine` if using MCP with `docker exec`

## License

MIT License. See [LICENSE](LICENSE) for details.
