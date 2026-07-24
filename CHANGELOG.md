# Changelog

Notable changes to Invoice Machine. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[semantic versioning](https://semver.org/) from 0.2.0 onward.

## [Unreleased]

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
