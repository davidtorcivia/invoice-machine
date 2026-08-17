# Security

## Reporting a vulnerability

Please report privately through
[GitHub's security advisory form](https://github.com/davidtorcivia/invoice-machine/security/advisories/new)
rather than opening a public issue.

Include what you did, what happened, and what you expected. A proof of concept
helps. Expect an acknowledgement within a week.

This is a single-maintainer hobby project with no bounty programme, but genuine
reports will be fixed and credited.

## What this app assumes

Invoice Machine is built for one administrator running one instance behind their
own reverse proxy. That shapes the model:

- **There is one user account.** There are no roles, no per-user data isolation,
  and no multi-tenancy. Anyone who authenticates sees everything.
- **You are expected to put an access layer in front of it.** Cloudflare Access,
  Tailscale, a VPN, or equivalent. The built-in login is a lock on the door, not
  a perimeter.
- **The database is trusted.** Anyone who can write to the SQLite file can do
  anything the app can.

## What is protected

| Area | Measure |
|------|---------|
| Passwords | PBKDF2-HMAC-SHA256, 600,000 iterations, per-user salt. Change password revokes every other session. |
| Sessions | Database-backed, 30-day expiry, revocable, `HttpOnly` cookies |
| CSRF | Double-submit cookie, required on every unsafe method |
| Stored credentials | SMTP, Stripe, and S3 secrets encrypted with Fernet; plaintext refused in production |
| API keys | Hashed at rest; plaintext keys refused in production |
| Stripe webhooks | HMAC signature with a 5-minute replay window, verified before the body is parsed |
| Brute force | Rate limits on every endpoint; a sliding-window throttle on bearer and MCP auth |
| File paths | PDF, logo, and backup access is confined to its directory and re-validated after resolution |
| Uploads | Image type determined by magic bytes, never the supplied filename; SVG rejected |
| Outbound requests | SMTP hosts and S3 endpoints resolving to loopback, link-local, or metadata addresses are refused |
| PDF rendering | WeasyPrint is restricted to inline `data:` URIs, so injected CSS cannot read local files or reach internal services |
| Headers | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` |

## Deployment expectations

In production the app refuses to start without `INVOICE_MACHINE_ENCRYPTION_KEY`.
Also set `SECURE_COOKIES=true`, point `CORS_ORIGINS` at your domain alone, and
keep the encryption key backed up separately from the database. Without the key,
stored credentials cannot be recovered.

Prefer a Stripe [restricted key](https://docs.stripe.com/keys/restricted-api-keys)
scoped to Checkout Sessions over a full secret key.

## Known limitations

These are accepted for the threat model above, and worth knowing:

- `X-Forwarded-For` and `CF-Connecting-IP` are trusted when present, so
  rate-limit keys can be spoofed if the app is exposed without a proxy that
  overwrites them.
- The outbound-host guard resolves DNS before connecting, so a rebinding
  attack between the two is theoretically possible.
- There is no audit log of administrative actions.
