# Invoicely: AI-First Invoicing App

## Overview

A minimal, self-hosted invoicing application designed for freelancers and small businesses. Primary interface is via MCP for AI-driven invoice management, with a clean web UI for manual operations and configuration.

**Target user:** Freelance colorist (single user, low volume, simple invoicing needs)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   Web UI    │  │  MCP Server │  │   PDF Generator │ │
│  │  (Svelte)   │  │  (stdio)    │  │   (Typst/CSS)   │ │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘ │
│         │                │                   │          │
│         └────────────────┼───────────────────┘          │
│                          ▼                              │
│                   ┌─────────────┐                       │
│                   │   SQLite    │                       │
│                   │   Database  │                       │
│                   └─────────────┘                       │
└─────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
    LAN / Cloudflare              Claude Desktop
       Tunnel                      (MCP Client)
```

### Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Backend | Python (FastAPI) | Simple, good SQLite support, easy MCP integration |
| Database | SQLite | Single file, no separate service, sufficient for low volume |
| Web UI | Svelte + TailwindCSS | Lightweight, fast, good DX |
| PDF Generation | WeasyPrint | Python-native, HTML/CSS templates, quality typography |
| MCP Server | Python (mcp package) | Native integration with Claude Desktop |
| Deployment | Docker Compose | Single container, easy to manage |

---

## Data Model

### Business Profile (singleton)

The user's business information. Only one record exists.

```sql
CREATE TABLE business_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Enforce singleton
    name TEXT NOT NULL,                      -- "David Torcivia"
    business_name TEXT,                      -- "David Torcivia LLC"
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT DEFAULT 'United States',
    email TEXT,
    phone TEXT,
    ein TEXT,                                -- Tax ID
    logo_path TEXT,                          -- Path to uploaded logo
    accent_color TEXT DEFAULT '#0891b2',     -- PDF accent color (teal)
    default_payment_terms_days INTEGER DEFAULT 30,
    default_notes TEXT,                      -- Default invoice footer
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Clients

```sql
CREATE TABLE clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,                               -- Contact name: "Jackie Swan"
    business_name TEXT,                      -- Company: "Google LLC"
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT,
    email TEXT,
    phone TEXT,
    payment_terms_days INTEGER DEFAULT 30,   -- Default Net 30
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP                     -- Soft delete (NULL = active)
);

CREATE INDEX idx_clients_deleted ON clients(deleted_at);
```

All fields optional except id. At minimum, user should provide either `name` or `business_name` to identify the client.

**Soft delete behavior:** Setting `deleted_at` moves client to trash. Clients with invoices can be trashed (invoices retain snapshot data). Trash auto-cleared after 90 days via scheduled task.

### Invoices

```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,     -- "20250623-1"
    client_id INTEGER REFERENCES clients(id),
    
    -- Denormalized client info (snapshot at invoice creation)
    client_name TEXT,
    client_business TEXT,
    client_address TEXT,
    client_email TEXT,
    
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'paid', 'overdue', 'cancelled')),
    
    issue_date DATE NOT NULL,                -- Can be backdated by user
    due_date DATE,
    payment_terms_days INTEGER DEFAULT 30,   -- Net 30 default
    currency_code TEXT DEFAULT 'USD',
    
    subtotal DECIMAL(10,2) NOT NULL DEFAULT 0,
    total DECIMAL(10,2) NOT NULL DEFAULT 0,
    
    notes TEXT,                              -- Footer notes
    
    pdf_path TEXT,                           -- Generated PDF location
    pdf_generated_at TIMESTAMP,              -- When PDF was last generated
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP                     -- Soft delete (NULL = active)
);

CREATE INDEX idx_invoices_date ON invoices(issue_date);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_client ON invoices(client_id);
CREATE INDEX idx_invoices_deleted ON invoices(deleted_at);
```

**Date handling:** `issue_date` is user-controllable and determines the invoice number prefix. `created_at` is the actual record creation timestamp (immutable). This allows backdating invoices while maintaining audit trail.

**PDF regeneration:** UI shows "Regenerate PDF" when `updated_at > pdf_generated_at`.
```

### Invoice Line Items

```sql
CREATE TABLE invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    total DECIMAL(10,2) NOT NULL,            -- quantity * unit_price
    sort_order INTEGER DEFAULT 0
);

CREATE INDEX idx_items_invoice ON invoice_items(invoice_id);
```

**Note:** Line items inherit currency from parent invoice. No per-item currency - all items on an invoice share the same `currency_code`.

---

## Invoice Numbering

Format: `YYYYMMDD-N` where N is sequential within that date.

Examples:
- First invoice on June 23, 2025: `20250623-1`
- Second invoice same day: `20250623-2`
- First invoice next day: `20250624-1`

**Generation logic:**
```python
def generate_invoice_number(issue_date: date) -> str:
    date_prefix = issue_date.strftime("%Y%m%d")
    
    # Find highest sequence for this date
    existing = db.query(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?",
        f"{date_prefix}-%"
    )
    
    # Robust parsing - ignore malformed numbers
    max_seq = 0
    for num in existing:
        try:
            parts = num.split('-')
            if len(parts) == 2 and parts[0] == date_prefix:
                max_seq = max(max_seq, int(parts[1]))
        except ValueError:
            continue  # Skip non-numeric suffixes
    
    return f"{date_prefix}-{max_seq + 1}"
```

**Note:** If user manually edits an invoice number to a non-standard format, the generator safely ignores it when calculating the next sequence.

---

## MCP Server Interface

The MCP server exposes tools for full invoice management. Claude Desktop connects via stdio.

### Tools

#### Business Profile

| Tool | Description |
|------|-------------|
| `get_business_profile` | Retrieve current business profile |
| `update_business_profile` | Update business profile fields |
| `upload_logo` | Upload/replace business logo (base64) |

#### Clients

| Tool | Description |
|------|-------------|
| `list_clients` | List all active clients (with optional search) |
| `get_client` | Get client by ID |
| `create_client` | Create new client |
| `update_client` | Update client fields |
| `delete_client` | Move client to trash |
| `restore_client` | Restore client from trash |

#### Invoices

| Tool | Description |
|------|-------------|
| `list_invoices` | List invoices with filters (status, date range, client) |
| `get_invoice` | Get invoice with line items |
| `create_invoice` | Create new invoice (issue_date can be backdated) |
| `update_invoice` | Update invoice (status, dates, notes) |
| `delete_invoice` | Move invoice to trash |
| `restore_invoice` | Restore invoice from trash |
| `add_invoice_item` | Add line item to invoice |
| `update_invoice_item` | Update line item |
| `remove_invoice_item` | Remove line item |
| `generate_pdf` | Generate/regenerate PDF, returns download URL |
| `list_trash` | List trashed invoices and clients |
| `empty_trash` | Permanently delete all trashed items |

### Example MCP Tool Definitions

```python
@mcp.tool()
async def create_invoice(
    client_id: int | None = None,
    client_name: str | None = None,
    client_business: str | None = None,
    client_email: str | None = None,
    issue_date: str | None = None,  # ISO format, defaults to today (can backdate)
    due_date: str | None = None,    # Auto-calculated from payment_terms if not set
    payment_terms_days: int = 30,
    currency_code: str = "USD",
    notes: str | None = None,
    items: list[dict] | None = None  # [{description, quantity, unit_price}]
) -> dict:
    """
    Create a new invoice.
    
    If client_id is provided, client info is pulled from the database.
    Otherwise, provide client details directly.
    Items can be added here or via add_invoice_item later.
    
    issue_date can be set to any date (for backdating). Invoice number
    is generated based on issue_date, not creation time.
    
    Returns the created invoice with generated invoice_number.
    """
    ...

@mcp.tool()
async def generate_pdf(invoice_id: int) -> dict:
    """
    Generate or regenerate PDF for an invoice.
    
    Returns:
        {
            "invoice_id": 123,
            "invoice_number": "20250115-1",
            "pdf_url": "{APP_BASE_URL}/api/invoices/123/pdf",
            "generated_at": "2025-01-15T10:30:00Z"
        }
    
    Note: pdf_url uses APP_BASE_URL env var for correct routing
    through LAN or Cloudflare Tunnel.
    """
    base_url = os.getenv("APP_BASE_URL", "http://localhost:8080")
    # ... generate PDF ...
    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice.invoice_number,
        "pdf_url": f"{base_url}/api/invoices/{invoice_id}/pdf",
        "generated_at": datetime.utcnow().isoformat()
    }

@mcp.tool()
async def list_invoices(
    status: str | None = None,       # draft, sent, paid, overdue, cancelled
    client_id: int | None = None,
    from_date: str | None = None,    # ISO format
    to_date: str | None = None,
    include_trashed: bool = False,
    limit: int = 50
) -> list[dict]:
    """
    List invoices with optional filters.
    Returns summary info (no line items).
    """
    ...
```

### Conversational Flow Example

User: "Create an invoice for Google for the Ancestra BTS color correction, $8000"

Claude's tool calls:
1. `list_clients(search="Google")` → finds client_id=1
2. `create_invoice(client_id=1, items=[{description: "Ancestra BTS Color Correction", quantity: 1, unit_price: 8000}])`
3. `generate_pdf(invoice_id=<new_id>)`

Claude responds: "Created invoice #20250115-1 for Google LLC - $8,000.00 for Ancestra BTS Color Correction. [Download PDF](http://localhost:8080/api/invoices/1/pdf)"

User: "Actually backdate that to December 15th"

Claude's tool calls:
1. `update_invoice(invoice_id=1, issue_date="2024-12-15")` → invoice_number changes to "20241215-1"
2. `generate_pdf(invoice_id=1)`

Claude responds: "Updated to invoice #20241215-1 with December 15th issue date. [Download updated PDF](http://localhost:8080/api/invoices/1/pdf)"

---

## Web UI

### Pages

1. **Dashboard** (`/`)
   - Summary stats (outstanding, paid this month, etc.)
   - Recent invoices list
   - Quick actions

2. **Invoices** (`/invoices`)
   - List view with filters
   - Status badges
   - Bulk actions (mark paid, etc.)

3. **Invoice Detail** (`/invoices/:id`)
   - Full invoice view
   - Edit mode
   - PDF preview/download
   - Status changes

4. **New Invoice** (`/invoices/new`)
   - Client selector (search/create inline)
   - Line item editor
   - Date pickers (including backdating)
   - Live preview

5. **Clients** (`/clients`)
   - List/search
   - CRUD operations

6. **Trash** (`/trash`)
   - Deleted invoices and clients
   - Restore / permanent delete
   - Shows auto-purge countdown (90 days)

7. **Settings** (`/settings`)
   - Business profile editor
   - Logo upload
   - Accent color picker
   - Invoice defaults (payment terms, notes template)

### Design Principles

- **Minimal chrome**: Content-focused, not feature-cluttered
- **Fast**: Client-side rendering, optimistic updates
- **Keyboard-friendly**: Shortcuts for common actions
- **Mobile-passable**: Not mobile-first, but usable

---

## PDF Template

Primary goal: **beautiful, professional output** that looks hand-crafted, not software-generated.

Based on the provided invoice samples. Clean, professional, single-page for typical invoices.

### Design Principles

- **Typography-first**: Generous whitespace, careful hierarchy, refined type scale
- **Minimal ornamentation**: No unnecessary borders, boxes, or visual noise
- **Print-ready**: High contrast, works in grayscale, clean at any size
- **Personality**: Subtle accent color, logo integration, doesn't look like generic template

### Layout

```
┌────────────────────────────────────────────────────┐
│  [LOGO]                                            │
│                                                    │
│  BUSINESS NAME                           INVOICE   │
│  Address                              #YYYYMMDD-N  │
│  Contact info                    Created: MM/DD/YY │
│                                                    │
├────────────────────────────────────────────────────┤
│  BILLED TO                                         │
│  Client Business                                   │
│  ATTN Contact Name                                 │
│  client@email.com                                  │
│                                                    │
├────────────────────────────────────────────────────┤
│  NO  ITEM DESCRIPTION          PRICE  QTY  SUBTOTAL│
│  ─────────────────────────────────────────────────│
│  01  Service description    $X,XXX.XX   1  $X,XXX │
│  02  Another service          $XXX.XX   2  $X,XXX │
│                                                    │
│                               SUBTOTAL    $XX,XXX │
│                               ─────────────────── │
│                               TOTAL      $XX,XXX  │
│                                                    │
├────────────────────────────────────────────────────┤
│  NOTICE                                            │
│  ─────────────────────────────────────────────────│
│  Payment notes, banking details, thank you, etc.   │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Styling

- Clean sans-serif font (Inter or similar)
- Accent color configurable (default: teal/cyan from sample)
- Minimal lines, whitespace-driven hierarchy
- High contrast for printability

---

## API Endpoints (Internal)

RESTful API consumed by the web UI. Same logic as MCP tools.

```
GET    /api/profile
PUT    /api/profile
POST   /api/profile/logo

GET    /api/clients
POST   /api/clients
GET    /api/clients/:id
PUT    /api/clients/:id
DELETE /api/clients/:id

GET    /api/invoices
POST   /api/invoices
GET    /api/invoices/:id
PUT    /api/invoices/:id
DELETE /api/invoices/:id
POST   /api/invoices/:id/items
PUT    /api/invoices/:id/items/:item_id
DELETE /api/invoices/:id/items/:item_id
POST   /api/invoices/:id/generate-pdf
GET    /api/invoices/:id/pdf
```

---

## Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

# WeasyPrint requires these system libraries (Cairo, Pango, GDK-Pixbuf)
# Do NOT use alpine - these deps are painful to install there
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY invoicely/ ./invoicely/
COPY frontend/build/ ./invoicely/static/

EXPOSE 8080

CMD ["uvicorn", "invoicely.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  invoicely:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data        # SQLite DB + PDFs + logos
    environment:
      - DATABASE_URL=sqlite:///app/data/invoicely.db
      - APP_BASE_URL=http://localhost:8080  # Override for LAN/tunnel access
      - TRASH_RETENTION_DAYS=90
    restart: unless-stopped
```

**APP_BASE_URL examples:**
- Local dev: `http://localhost:8080`
- LAN access: `http://192.168.1.50:8080`
- Cloudflare Tunnel: `https://invoices.yourdomain.com`

MCP tools use this for PDF links, so Claude presents working URLs regardless of where the server runs.

### Scheduled Tasks

Run via container cron or external scheduler:

```bash
# Empty trash older than 90 days (runs daily)
0 3 * * * docker exec invoicely python -m invoicely.tasks.cleanup_trash

# Optional: SQLite backup
0 4 * * * docker exec invoicely sqlite3 /app/data/invoicely.db ".backup /app/data/backups/invoicely-$(date +%Y%m%d).db"
```

### Cloudflare Tunnel + Access (Required)

**⚠️ Do not expose without authentication.**

The app has no built-in auth. Use Cloudflare Access (Zero Trust) to gate access:

1. Create tunnel:
```bash
cloudflared tunnel create invoicely
cloudflared tunnel route dns invoicely invoices.yourdomain.com
```

2. Configure Access policy in Cloudflare dashboard:
   - Application: `invoices.yourdomain.com`
   - Policy: Allow specific email (your email) via OTP or identity provider

3. Add to docker-compose or run separately:
```yaml
  cloudflared:
    image: cloudflare/cloudflared
    command: tunnel run invoicely
    volumes:
      - ./cloudflared:/etc/cloudflared
    restart: unless-stopped
```

For LAN-only access without Cloudflare, bind to local interface only (`127.0.0.1:8080`).

### MCP Configuration

**Option A: Local Docker (same machine as Claude Desktop)**

Add to Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "invoicely": {
      "command": "docker",
      "args": ["exec", "-i", "invoicely", "python", "-m", "invoicely.mcp"]
    }
  }
}
```

**Option B: Remote server (different machine)**

If running on a VPS or home server, expose MCP over SSE:

```json
{
  "mcpServers": {
    "invoicely": {
      "url": "https://invoices.yourdomain.com/mcp/sse"
    }
  }
}
```

Requires implementing SSE transport endpoint in FastAPI (protected by Cloudflare Access).

---

## File Structure

```
invoicely/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
│
├── invoicely/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Settings
│   ├── database.py          # SQLite setup + models
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── profile.py
│   │   ├── clients.py
│   │   └── invoices.py
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── server.py        # MCP tool definitions
│   │
│   ├── pdf/
│   │   ├── __init__.py
│   │   ├── generator.py
│   │   ├── template.html    # Jinja2 template
│   │   └── style.css        # PDF styles (WeasyPrint)
│   │
│   └── static/              # Built frontend assets
│
├── frontend/
│   ├── package.json
│   ├── svelte.config.js
│   ├── src/
│   │   ├── routes/
│   │   ├── lib/
│   │   └── app.html
│   └── static/
│
└── data/                    # Docker volume mount point
    ├── invoicely.db
    ├── pdfs/
    └── logos/
```

---

## Out of Scope (v1)

- Multi-user / authentication
- Recurring invoices
- Time tracking
- Expense tracking
- Multi-currency
- Tax calculations (VAT, sales tax)
- Payment integrations (Stripe, etc.)
- Email sending (generate PDF, user sends manually)
- Reporting / analytics beyond basic counts

---

## Resolved Decisions

| Question | Decision |
|----------|----------|
| PDF engine | WeasyPrint (Python-native, HTML/CSS templates) |
| Invoice editing | Allow edits, track with `pdf_generated_at`, show regenerate prompt |
| Backup | SQLite + volume mount, user manages backups |
| Logo storage | Filesystem (`data/logos/`) |
| Authentication | Cloudflare Access (Zero Trust) - required for public exposure |
| Invoice numbering | `YYYYMMDD-N` format (date-based sequential) |
| Payment terms | Default Net 30, configurable per client and invoice |
| Deletion | Soft delete to trash, auto-purge after 90 days |
| Accent color | Configurable in business_profile, passed to PDF template via CSS variable |
| Due date | Auto-calculated: `issue_date + payment_terms_days` (user can override) |

---

## Due Date Calculation Logic

```python
def calculate_due_date(
    issue_date: date,
    payment_terms_days: int | None = None,
    explicit_due_date: date | None = None,
    client: Client | None = None,
    business: BusinessProfile
) -> date:
    # Explicit override takes precedence
    if explicit_due_date:
        return explicit_due_date
    
    # Determine payment terms: invoice -> client -> business default
    terms = (
        payment_terms_days 
        or (client.payment_terms_days if client else None)
        or business.default_payment_terms_days
        or 30
    )
    
    return issue_date + timedelta(days=terms)
```

---

## PDF Template CSS Variables

```css
:root {
  --accent-color: {{ business.accent_color | default('#0891b2') }};
}

.invoice-header { border-bottom: 3px solid var(--accent-color); }
.total-row { color: var(--accent-color); }
```

---

## Implementation Phases

### Phase 1: Core Backend
- Database schema + migrations
- Business profile CRUD
- Client CRUD
- Invoice CRUD with line items
- Invoice number generation

### Phase 2: MCP Server
- Tool definitions
- stdio transport
- Testing with Claude Desktop

### Phase 3: PDF Generation
- Template design
- Generator implementation
- Logo integration

### Phase 4: Web UI
- Svelte app scaffold
- Invoice list + detail views
- Client management
- Settings page

### Phase 5: Polish + Deploy
- Docker packaging
- Cloudflare tunnel docs
- README / usage guide