# Invoice Machine

A self-hosted invoicing application for freelancers and small businesses. Create invoices and quotes, manage clients, and generate PDFs.

## Features

- Create and track invoices and quotes with automatic numbering
- Client database with address and payment terms
- PDF generation with customizable branding and logo
- Built-in authentication with rate limiting
- Automatic daily backups with optional S3 storage
- Dark mode with system preference detection
- Overdue invoice highlighting
- MCP integration for Claude Desktop
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

Set these in a `.env` file or as environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | External port mapping | `8080` |
| `DATA_DIR` | Directory for data storage | `./data` |
| `APP_BASE_URL` | Base URL for the application | `http://localhost:8080` |
| `TRASH_RETENTION_DAYS` | Days before auto-purge from trash | `90` |

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
      "transport": "sse",
      "url": "https://your-server/mcp/sse",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

The MCP endpoint runs on the same port as the web app. Works with Cloudflare Tunnel or any reverse proxy.

### Local Docker Setup

If running locally, you can use stdio transport:

```json
{
  "mcpServers": {
    "invoice-machine": {
      "command": "docker",
      "args": ["exec", "-i", "invoice-machine", "python", "-m", "invoicely.mcp.server"]
    }
  }
}
```

### Example Commands

- "Create an invoice for Acme Corp for website development, 40 hours at $150/hour"
- "Create a quote for logo design $500, brand guidelines $1200"
- "List all unpaid invoices from last month"
- "Mark invoice 20250115-1 as paid"
- "Generate PDF for all draft invoices"

### MCP Tools

**Business Profile:** `get_business_profile`, `update_business_profile`, `add_payment_method`, `remove_payment_method`

**Clients:** `list_clients`, `get_client`, `create_client`, `update_client`, `delete_client`, `restore_client`

**Invoices:** `list_invoices`, `get_invoice`, `create_invoice`, `update_invoice`, `delete_invoice`, `restore_invoice`

**Line Items:** `add_invoice_item`, `update_invoice_item`, `remove_invoice_item`

**Other:** `generate_pdf`, `list_trash`, `empty_trash`

## Project Structure

```
invoice-machine/
├── invoicely/           # Python backend
│   ├── api/             # FastAPI routes
│   ├── mcp/             # MCP server
│   ├── pdf/             # PDF generation
│   ├── database.py      # SQLAlchemy models
│   ├── services.py      # Business logic
│   └── main.py          # FastAPI app
├── frontend/            # SvelteKit frontend
├── data/                # Runtime data (gitignored)
│   ├── invoicely.db     # SQLite database
│   ├── pdfs/            # Generated PDFs
│   └── logos/           # Uploaded logos
└── docker-compose.yml
```

## Development

### Backend

```bash
pip install -e ".[dev]"
uvicorn invoicely.main:app --reload --port 8080
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

## Deployment

For remote access, use a reverse proxy. Example with Cloudflare Tunnel:

1. `cloudflared tunnel create invoice-machine`
2. Configure Access policy in Cloudflare dashboard
3. Set `APP_BASE_URL` in `.env`

## License

MIT License. See [LICENSE](LICENSE) for details.
