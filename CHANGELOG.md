# Changelog

Notable changes to Invoice Machine. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[semantic versioning](https://semver.org/) from 0.2.0 onward.

## [Unreleased]

### Changed

- Multiple MCP and bot API keys, each labeled and rotated or revoked on its own,
  under Settings > MCP Integration and Settings > Bot API Key. Existing keys keep
  working and appear as "Migrated MCP key" and "Migrated bot key".
- Bot API keys no longer reach `/api/backups`. A restore would resurrect revoked
  keys, and a download-edit-restore cycle could forge a web session, so backups
  are web-session-only like key management. The bot skill manifest no longer
  lists them.
- `PDF_DIR` and `LOGO_DIR` are gone; both derive from `DATA_DIR`.
- Line item unit prices are quantized to two decimals on save, so the printed
  unit price times quantity equals the line total.
- `paid_at` is the latest payment date, not the moment the payment was recorded,
  so "paid this month" reflects when the money arrived.
- MCP tools report a missing record as an MCP tool error (`isError`) instead of
  a `success: false` dict; validation failures roll back the session and use the
  same error type.
- Reusing a payment `idempotency_key` against a different invoice is an error
  instead of silently returning the other invoice's payment.
- A database created before Alembic (application tables but no
  `alembic_version`) is refused at startup with instructions to migrate it by
  hand (`alembic stamp 001_initial`, then `alembic upgrade head`). It was
  previously given a few missing columns and stamped current, which marked a
  database still missing every table added since as up to date.
- The startup catch-up jobs (overdue check, recurring invoices, payment
  reminders) run only in the worker holding the scheduler lock, so a second
  worker cannot generate the same recurring invoices at boot.
- Minimum versions: `python-multipart` 0.0.31, `weasyprint` 68, `cryptography`
  48.0.1. CI tests on Python 3.11 and 3.14, the version the image ships.

### Fixed

- Locked dependencies upgraded (starlette 1.6, fastapi 0.141, mcp 2.1.1,
  pydantic 2.13, pillow 12.3, urllib3 2.7); the previous lock carried 53 known
  advisories. The CI dependency audit now blocks a merge instead of warning.
- Builds are reproducible: the Docker image and CI install exactly `uv.lock`
  (`uv sync --frozen`) instead of resolving `pyproject.toml` floors afresh, and
  CI fails when the lockfile is stale. The dependency audit checks the locked
  tree.
- A failed line-item search index rebuild dropped the old index first and left
  search on the slow LIKE fallback until the next rebuild. The new index is now
  built and populated before the old one is replaced.
- `GET /mcp/status` returned 500 since the MCP 2026-07-28 upgrade (#24).
- Production emitted no application logs after startup: the in-process Alembic
  upgrade reset the root logger.
- One failing reminder or recurring schedule aborted the rest of the sweep with
  `MissingGreenlet`; each item is now re-fetched after a rollback.
- Two simultaneous payments could overpay an invoice past the overpayment guard.
- Creating an invoice for a nonexistent client retried six times and reported
  an invoice-number collision.
- A paid, partially paid, or converted document could be flipped between quote
  and invoice.
- Sent quotes were marked overdue by the nightly job.
- Each reminder bumped `updated_at`, forcing a PDF re-render on the next fetch.
- The pre-restore safety copy was a raw file copy that could miss uncheckpointed
  WAL data; it now uses the online backup API.
- MCP `add_invoice_item` raised on a missing invoice instead of returning an
  error.
- A Stripe checkout paid in a different currency than the invoice is logged and
  skipped instead of recorded against the invoice.
- Editing payment terms on an existing invoice was silently ignored.
- Clearing an optional client or profile field (email, phone, address, notes,
  app base URL) did not save; the old value came back on reload.
- Saving an invoice edit form opened before a Stripe payment arrived reverted
  the invoice to unpaid.
- Recording a payment shared the payment list's rate limit and could return 429
  after the payment was committed.

## [0.3.0]

### Added

- Password change from Settings > Account. Other sessions are revoked; the
  current session stays signed in.
- Marking an invoice paid now records the outstanding balance as a payment so
  the ledger, Stripe links, and amount-due stay consistent.

### Fixed

- SMTP STARTTLS used Python's default `CERT_NONE` context, so a mail server
  certificate was never verified. It now uses `ssl.create_default_context()`.
- A stored SMTP password that failed to decrypt was sent to the server as the
  ciphertext itself. That now fails with a re-save instruction.
- Emailing an invoice joined `data_dir` to the stored `pdf_path` without
  confinement, unlike the PDF download endpoint.
- Adding a line item to a fully-paid invoice left the status as paid after the
  new total exceeded `amount_paid`.
- A concurrent Stripe webhook that raced past the external-id lookup could 500
  instead of returning the payment the unique index already recorded.
- FastAPI validation errors surfaced in the UI as `[object Object]`.
- Document title was missing for Reports, Recurring, and Email Templates.
- Package/app version still said `0.1.0` after the 0.2.0 release.

### Changed

- `CF-Connecting-IP` and `X-Forwarded-For` are ignored unless
  `TRUST_PROXY_HEADERS=true`. Set that behind Cloudflare or another proxy that
  overwrites the headers.
- Hashed MCP/bot API keys and encrypted SMTP passwords now declare column
  widths that actually fit the stored values (`hash:<salt>:<digest>` is 102
  characters; Fernet ciphertext of a long SMTP password exceeds 255).
- Logo, PDF, and backup path checks go through one `confined_file` helper that
  uses `Path.relative_to` rather than a string prefix.
- A successful login upgrades a leftover SHA-256 password hash to PBKDF2.
- Two concurrent first-run `/setup` requests can no longer create two admins.
- Client-page outstanding used the paper total and ignored partial payments.
- The record-payment modal seeded $0 because it mounted before the invoice
  balance was known.
- Fully prepaid sent invoices were still flipped to overdue.
- Production now refuses to start without `INVOICE_MACHINE_ENCRYPTION_KEY`, and
  hides `/docs` / OpenAPI.
- A failed `/auth/status` no longer dumps a first-run user onto the login page.
- S3 backup endpoints resolving to loopback or link-local addresses are refused,
  matching the SMTP SSRF guard.
- Quote-to-invoice conversion and recurring generation now commit the new
  invoice and the schedule/quote link in one transaction. A quote can convert
  only once (`uq_invoices_converted_from`).
- Reminder sweeps align to the UTC hour boundary and run once at startup, so a
  restart no longer skips the send hour.
- Purging trash no longer 500s when a recurring schedule still pointed at a
  deleted invoice.
- Removed the drifted `designdoc.md`. README is the source of truth.
- Session cookies are stored as SHA-256 digests. Leftover plaintext rows are
  upgraded on the next request. A stored digest presented as the cookie is
  rejected.
- Add-item is a JSON body, not query parameters.
- Overdue and recurring "today" use the business timezone.
- Unused frontend data stores and the no-op `hooks.server.js` are gone.
- `npm audit` high (nanoid) is patched.

## [0.2.0]

### Fixed (in this release)

- Dashboard and revenue "outstanding" totals summed the full invoice total for
  sent/overdue invoices, ignoring partial payments — a half-paid invoice was
  reported as fully owed. Both now report the balance still owed, consistent
  with A/R aging and the consolidated roll-up.
- Payments and payment links could be recorded against quotes. The UI and PDF
  already treated quotes as unpayable; the API, MCP tools and webhook path now
  enforce it too, with a clear error pointing at quote conversion.

### Added

- **Payment tracking with partial payments.** Record what clients actually pay,
  against a running balance. An invoice settles itself once payments cover the
  total, and reverts to sent or overdue if a payment is removed.
- **Accounts receivable aging.** Outstanding balances bucketed by how far past
  due, per currency, with the overdue invoices listed.
- **Hosted card payments through Stripe.** A Checkout link per invoice covering
  the outstanding balance, appearing on the PDF and in emails. Completed
  payments are reconciled through a signature-verified webhook.
- **Automated payment reminders** on a schedule of day offsets around the due
  date, sent in the business's own timezone at a chosen hour.
- **CSV export** of invoices, line items, payments and clients.
- **Quote to invoice conversion** that keeps the quote as the accepted record
  and links the two documents.
- **Per-invoice exchange rates** captured at issue time, with an opt-in
  single-currency roll-up that reports what it could not convert.
- `CONTRIBUTING.md`, `SECURITY.md`, issue and pull request templates,
  Dependabot, and an `.editorconfig`.
- A dependency-free browser smoke test (`npm run test:smoke`) that drives the
  running app and fails on any console error, plus API typedefs kept honest by
  a contract test against the serializers.

### Changed

- CI now builds the Docker image and boots it, checks formatting, runs against
  two Python versions, and audits dependencies. The coverage gate moved from
  60% to 70%.
- The in-app help was rewritten for the features above and corrected in two
  places where it described behaviour the app no longer had.
- The README was rewritten and shortened.
- Backups are now a tar archive containing the database and your uploaded
  logos. Database-only backups from earlier versions still restore.

### Fixed

- **Every PDF fetch re-rendered the document.** `updated_at`'s `onupdate`
  default is applied at flush time, always landing after the `pdf_generated_at`
  written in the same statement, so an invoice was permanently stale.
- **Distinct invoice numbers could share one PDF file.** Filename sanitization
  drops dots, so `INV.001` and `INV001` collided and one invoice's PDF could be
  served or emailed for another.
- **Recurring schedule settings were silently discarded.** The yearly month,
  quarterly month, payment instructions and auto-email options existed in the
  UI and the database but were never mapped on the model, so a schedule set to
  bill yearly in March billed in whatever month it was created.
- **Editing any recurring schedule field reset the next invoice date**, skipping
  or duplicating a billing period.
- **Restoring a backup did not apply migrations**, so a backup from an older
  release came back with missing columns.
- **Invoices marked paid before payment tracking existed reported a full balance
  due.** Migration 015 backfills them.
- Three-decimal currencies (BHD, JOD, KWD, OMR, TND) were charged as if they had
  two decimal places, undercharging by a factor of ten.
- `default_tax_rate` accepted arbitrary strings: a non-numeric value returned
  500, and `999` silently set a 999% default rate on every new invoice.
- Purging the trash left generated PDFs on disk; uploading a logo left the
  previous file behind.
- The email `From` header was assembled by string interpolation, so a comma or
  angle bracket in the display name forged or broke the address.
- Search fell back from full-text to a `LIKE` scan silently, and did not escape
  SQL wildcards in the user's query.
- Sixteen endpoints had no rate limit, including the PDF route that can trigger
  a full render.
- Restoring a backup lost your uploaded logo, because backups held only the
  database while the restored rows still referenced the file.
- The Content Security Policy only allowed the app's own bootstrap script when
  a Cloudflare header was present, so any deployment not behind Cloudflare
  served a blank page.
- The recurring schedule modal never offered its auto-email option, because it
  read SMTP status from an endpoint that does not return it.

### Security

- Stripe credentials and webhook secrets are encrypted at rest and never
  returned by the API.
- The webhook endpoint verifies an HMAC signature with a replay window before
  parsing the request body, and records each event at most once.
- Logo uploads take their file type from magic bytes rather than the supplied
  filename.

## [0.1.0]

Initial release: invoices and quotes, clients, PDF generation, recurring
schedules, tax, SMTP delivery, full-text search, backups, analytics, MCP server,
and a bot API.
