# Invoice Machine Bot Skill

Automate invoicing, client management, recurring billing, analytics, and more over HTTP.

## Authentication

Every request requires a Bot API Key in the `Authorization` header:

```
Authorization: Bearer <BOT_API_KEY>
```

Generate one from the web UI at **Settings > Bot API Key**, or via:

```
POST __BASE_URL__/api/profile/bot-key
```

The key is shown once. Store it securely.

## Base URL

```
__BASE_URL__/api
```

All endpoints below are relative to this base unless noted otherwise.

## Content Type

- Send JSON bodies with `Content-Type: application/json`
- Responses are JSON unless noted (e.g. PDF download)

---

## Business Profile

### Get profile
```
GET /api/profile
```
Returns business name, address, contact info, tax defaults, payment methods, accent color, default notes, SMTP status, and email template settings.

### Update profile
```
PUT /api/profile
```
Body (all fields optional):
```json
{
  "name": "Your Name",
  "business_name": "Acme LLC",
  "address_line1": "123 Main St",
  "address_line2": "Suite 4",
  "city": "Springfield",
  "state": "IL",
  "postal_code": "62701",
  "country": "US",
  "email": "you@example.com",
  "phone": "+1-555-0100",
  "ein": "12-3456789",
  "accent_color": "#0891b2",
  "default_payment_terms_days": 30,
  "default_notes": "Thank you for your business!",
  "default_payment_instructions": "Pay via ACH or check",
  "default_currency_code": "USD",
  "theme_preference": "system",
  "default_tax_enabled": true,
  "default_tax_rate": 8.25,
  "default_tax_name": "Sales Tax",
  "payment_methods": "[...]"
}
```

### Upload logo
```
POST /api/profile/logo
Content-Type: multipart/form-data
```
Field: `file` (PNG, JPG, JPEG, GIF, or WEBP).

### Delete logo
```
DELETE /api/profile/logo
```

### Generate / delete API keys
```
POST /api/profile/bot-key      → {"bot_api_key": "im_bot_..."}
DELETE /api/profile/bot-key

POST /api/profile/mcp-key      → {"mcp_api_key": "im_mcp_..."}
DELETE /api/profile/mcp-key
```

---

## Clients

### List clients
```
GET /api/clients?search=acme&include_deleted=false
```

### Create client
```
POST /api/clients
```
```json
{
  "name": "Jane Doe",
  "business_name": "Acme Corp",
  "address_line1": "456 Oak Ave",
  "city": "Portland",
  "state": "OR",
  "postal_code": "97201",
  "country": "US",
  "email": "jane@acme.com",
  "phone": "+1-555-0200",
  "payment_terms_days": 30,
  "notes": "Net 30, prefers email",
  "preferred_currency": "USD",
  "tax_enabled": 1,
  "tax_rate": 8.25,
  "tax_name": "Sales Tax"
}
```
`tax_enabled`: `null` = use global default, `0` = disabled, `1` = enabled.

### Get client
```
GET /api/clients/{id}
```

### Update client
```
PUT /api/clients/{id}
```
Body: same fields as create, all optional.

### Delete client (soft)
```
DELETE /api/clients/{id}
```
Returns `204`. Client moves to trash.

### Restore client
```
POST /api/clients/{id}/restore
```

---

## Invoices & Quotes

### List invoices
```
GET /api/invoices?status=draft&client_id=1&from_date=2025-01-01&to_date=2025-12-31&sort_by=issue_date&sort_dir=desc&limit=50
```
`sort_by`: `created_at` | `issue_date` | `due_date` | `client` | `invoice_number` | `total` | `status`

### List invoices (paginated)
```
GET /api/invoices/paginated?page=1&per_page=25&status=sent&document_type=invoice
```
Returns `{"items": [...], "pagination": {"page": 1, "per_page": 25, "total": 42, "total_pages": 2, "has_next": true, "has_prev": false}}`.

### List clients (paginated)
```
GET /api/clients/paginated?page=1&per_page=25&search=acme
```
Returns `{"clients": [...], "page": 1, "per_page": 25, "total": 42, "total_pages": 2, "has_next": true, "has_prev": false}`.

### Create invoice or quote
```
POST /api/invoices
```
```json
{
  "client_id": 1,
  "issue_date": "2025-06-15",
  "due_date": "2025-07-15",
  "payment_terms_days": 30,
  "currency_code": "USD",
  "notes": "Due upon receipt",
  "document_type": "invoice",
  "client_reference": "PO-4567",
  "show_payment_instructions": true,
  "selected_payment_methods": "[\"pm_id_1\",\"pm_id_2\"]",
  "invoice_number_override": "CUSTOM-001",
  "tax_enabled": true,
  "tax_rate": 8.25,
  "tax_name": "Sales Tax",
  "items": [
    {"description": "Consulting", "quantity": 10, "unit_price": 150.00, "unit_type": "hours"},
    {"description": "License fee", "quantity": 1, "unit_price": 500.00, "unit_type": "qty"}
  ]
}
```
- `document_type`: `"invoice"` (default) or `"quote"` (uses Q-YYYYMMDD-N numbering).
- `unit_type`: `"qty"` (default) or `"hours"`.
- Omit `issue_date` to default to today. Omit `due_date` to auto-calculate from `payment_terms_days`.
- Omit `invoice_number_override` for auto-generated numbers (YYYYMMDD-N format).
- Items are optional; you can add them later.

### Get invoice
```
GET /api/invoices/{id}
```
Returns full invoice with line items.

### Update invoice
```
PUT /api/invoices/{id}
```
```json
{
  "status": "sent",
  "issue_date": "2025-06-20",
  "due_date": "2025-07-20",
  "notes": "Updated terms",
  "document_type": "invoice",
  "client_reference": "PO-9999",
  "show_payment_instructions": true,
  "selected_payment_methods": "[\"pm_id_1\"]",
  "tax_enabled": true,
  "tax_rate": 10.0,
  "tax_name": "VAT"
}
```
`status`: `draft` | `sent` | `paid` | `overdue` | `cancelled`
Note: Changing `issue_date` regenerates the invoice number.

### Delete invoice (soft)
```
DELETE /api/invoices/{id}
```

### Restore invoice
```
POST /api/invoices/{id}/restore
```

### Bulk actions
```
POST /api/invoices/bulk
```
```json
{
  "action": "mark_paid",
  "invoice_ids": [1, 2, 3]
}
```
`action`: `mark_sent` | `mark_paid` | `delete`. Max 100 IDs per request.

---

## Line Items

### Add item
```
POST /api/invoices/{id}/items?description=Consulting&quantity=10&unit_price=150.00&unit_type=hours
```

### Update item
```
PUT /api/invoices/{invoice_id}/items/{item_id}
```
```json
{"description": "Updated", "quantity": 5, "unit_price": 200.00, "unit_type": "hours"}
```

### Remove item
```
DELETE /api/invoices/{invoice_id}/items/{item_id}
```

---

## PDF Generation

### Generate / regenerate PDF
```
POST /api/invoices/{id}/generate-pdf
```
Returns `{"invoice_id": 1, "invoice_number": "20250615-1", "pdf_url": "...", "generated_at": "..."}`.

### Download PDF
```
GET /api/invoices/{id}/pdf
```
Returns the PDF file directly (`application/pdf`). Auto-generates if missing or stale.

---

## Email

Requires SMTP to be configured (see SMTP Settings below).

### Send invoice email
```
POST /api/invoices/{id}/send-email
```
```json
{
  "recipient_email": "client@example.com",
  "subject": "Invoice #20250615-1",
  "body": "Please find your invoice attached."
}
```
All fields optional — defaults to client's email and saved templates. PDF is auto-generated if needed. Draft invoices are automatically marked as `sent` on success.

### Preview email (template expansion)
```
POST /api/invoices/{id}/email-preview
```
```json
{
  "subject_template": "Invoice {invoice_number} from {business_name}",
  "body_template": "Hi {client_name},\\n\\nPlease find invoice {invoice_number} for {total}."
}
```
Returns the expanded subject and body without sending.

### Get email templates
```
GET /api/settings/email-templates
```
Returns current templates, defaults, and available placeholders:
`{invoice_number}`, `{quote_number}`, `{document_type}`, `{client_name}`, `{client_business_name}`, `{client_email}`, `{total}`, `{amount}`, `{subtotal}`, `{due_date}`, `{issue_date}`, `{your_name}`, `{business_name}`.

### Update email templates
```
PUT /api/settings/email-templates
```
```json
{
  "email_subject_template": "Invoice {invoice_number} from {business_name}",
  "email_body_template": "Hi {client_name},\\n\\nAttached is invoice {invoice_number} for {total}, due {due_date}."
}
```
Set to empty string `""` to reset to defaults.

---

## SMTP Settings

### Get SMTP settings
```
GET /api/settings/smtp
```

### Update SMTP settings
```
PUT /api/settings/smtp
```
```json
{
  "smtp_enabled": true,
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "smtp_username": "user@example.com",
  "smtp_password": "secret",
  "smtp_from_email": "invoices@example.com",
  "smtp_from_name": "Acme Billing",
  "smtp_use_tls": true
}
```

### Test SMTP connection
```
POST /api/settings/smtp/test
```

---

## Recurring Invoices

### List schedules
```
GET /api/recurring?client_id=1&active_only=true
```

### Create schedule
```
POST /api/recurring
```
```json
{
  "client_id": 1,
  "name": "Monthly Retainer",
  "frequency": "monthly",
  "schedule_day": 1,
  "currency_code": "USD",
  "payment_terms_days": 30,
  "notes": "Recurring monthly charge",
  "next_invoice_date": "2025-07-01",
  "tax_enabled": 1,
  "tax_rate": 8.25,
  "tax_name": "Sales Tax",
  "line_items": [
    {"description": "Monthly retainer", "quantity": 1, "unit_price": 2000.00, "unit_type": "qty"}
  ]
}
```
`frequency`: `daily` | `weekly` | `monthly` | `quarterly` | `yearly`
`schedule_day`: day of month (1-31) for monthly/quarterly/yearly, or day of week (0=Mon, 6=Sun) for weekly.

### Get schedule
```
GET /api/recurring/{id}
```

### Update schedule
```
PUT /api/recurring/{id}
```
Body: same fields as create, all optional. Also accepts `is_active`.

### Delete schedule
```
DELETE /api/recurring/{id}
```

### Pause / resume
```
POST /api/recurring/{id}/pause
POST /api/recurring/{id}/resume
```

### Trigger now
```
POST /api/recurring/{id}/trigger
```
Manually creates an invoice from the schedule and advances the next date.

---

## Analytics

### Revenue summary
```
GET /api/analytics/revenue?from_date=2025-01-01&to_date=2025-12-31&group_by=month
```
`group_by`: `month` | `quarter` | `year`
Returns totals (invoiced, paid, outstanding, draft, overdue) and breakdown by period.

### Client lifetime value
```
GET /api/analytics/clients?limit=20
GET /api/analytics/clients?client_id=1
```
Returns total invoiced, total paid, invoice counts, first/last invoice dates per client.

---

## Search

```
GET /api/search?q=consulting&invoices=true&clients=true&line_items=true&limit=20
```
Full-text search (FTS5) across invoices, clients, and line items. Returns categorized results.

---

## Trash

### List trashed items
```
GET /api/trash
```
Returns items with `days_until_purge` (auto-purge after 90 days).

### Empty trash
```
POST /api/trash/empty
```
Permanently deletes all trashed items. **Irreversible.**

### Restore from trash
```
POST /api/trash/restore/{type}/{id}
```
`type`: `client` | `invoice`

---

## Backups

### Get backup settings
```
GET /api/backups/settings
```

### Update backup settings
```
PUT /api/backups/settings
```
```json
{
  "backup_enabled": true,
  "backup_retention_days": 30,
  "backup_s3_enabled": true,
  "backup_s3_endpoint_url": "https://s3.amazonaws.com",
  "backup_s3_access_key_id": "AKIA...",
  "backup_s3_secret_access_key": "...",
  "backup_s3_bucket": "my-backups",
  "backup_s3_region": "us-east-1",
  "backup_s3_prefix": "invoice-machine/"
}
```

### List backups
```
GET /api/backups?include_s3=true
```

### Create backup
```
POST /api/backups?compress=true
```

### Restore from backup
```
POST /api/backups/restore/{filename}?download_from_s3=false
```
Creates a pre-restore backup automatically.

### Download backup file
```
GET /api/backups/download/{filename}
```

### Delete backup
```
DELETE /api/backups/{filename}
```

### Clean up old backups
```
POST /api/backups/cleanup
```

### Test S3 connection
```
POST /api/backups/test-s3
```

---

## Typical Workflows

### Create and send an invoice
```bash
# 1. Create client (or skip if exists)
POST /api/clients
  {"business_name": "Acme Corp", "email": "billing@acme.com", "payment_terms_days": 30}

# 2. Create invoice with items
POST /api/invoices
  {"client_id": 1, "items": [{"description": "Consulting", "quantity": 10, "unit_price": 150, "unit_type": "hours"}]}

# 3. Generate PDF
POST /api/invoices/1/generate-pdf

# 4. Send via email (auto-marks as sent)
POST /api/invoices/1/send-email
```

### Set up recurring billing
```bash
# Create a monthly schedule
POST /api/recurring
  {"client_id": 1, "name": "Monthly Retainer", "frequency": "monthly", "schedule_day": 1,
    "line_items": [{"description": "Retainer", "quantity": 1, "unit_price": 2000}]}

# Invoices are created automatically. To trigger manually:
POST /api/recurring/1/trigger
```

### Check revenue
```bash
GET /api/analytics/revenue?from_date=2025-01-01&group_by=quarter
GET /api/analytics/clients?limit=10
```

---

## Error Responses

Errors return JSON with a `detail` field:
```json
{"detail": "Client not found"}
```
Common HTTP status codes: `400` (bad request), `401` (unauthorized), `404` (not found), `422` (validation error), `429` (rate limited).

## Rate Limits

Most read endpoints allow 60-120 requests/minute. Write endpoints are more restrictive (10-60/hour). The `Retry-After` header indicates when to retry after a `429`.

