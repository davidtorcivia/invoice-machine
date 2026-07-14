# Optional payment providers

Invoice Machine has a provider-neutral payment ledger. Manual payments, partial
balances, refunds, reminder eligibility, and reporting do not depend on Stripe or any
other third party. Provider support is an adapter at the edge of the application.

## Product contract

- Providers are disabled by default.
- A self-hoster supplies and owns all provider credentials.
- The base Python and Docker installs do not install a provider SDK.
- No provider network request occurs unless a provider is configured, globally enabled,
  and used for an eligible invoice.
- Hosted checkout is preferred so Invoice Machine never handles card data.
- Signed webhook events are the authority for settled, refunded, and disputed funds.
- Provider event IDs and payment IDs are unique and replay-safe.
- Checkout creation must honor `CheckoutRequest.idempotency_key`. Invoice Machine
  atomically claims and reuses one active session per invoice balance so repeated
  payment-link visits cannot create multiple payable sessions.
- Adapters must implement `expire_checkout` so Invoice Machine can revoke the
  external session before rotating a payment token or replacing a stale claim.
- All refund requests require an `Idempotency-Key` header. Clients must reuse the same
  key when retrying an ambiguous request; the key is durably recorded before any
  balance change and forwarded to the provider when applicable.
- Manual payments continue to work when providers are absent or unavailable.

## Architecture

Adapters implement `PaymentProvider` in `invoice_machine/payments/base.py`. Provider
selection and credential decryption live in `invoice_machine/payments/registry.py`.
Business rules and invoice balance synchronization live in
`invoice_machine/service/payments.py`; adapters must not change invoice status directly.

To add a provider:

1. Add an optional dependency extra in `pyproject.toml`; never add its SDK to the base
   dependencies.
2. Implement hosted checkout, checkout expiration, signature verification, refund
   initiation, and connection testing behind the provider protocol.
3. Map provider webhooks into `ProviderEvent` without trusting client-supplied amounts.
4. Register the adapter and add encrypted credential fields without returning secrets in
   API responses.
5. Add unit tests for exact currency conversion, invalid signatures, replays, delayed
   events, duplicate payment IDs, refunds, and disputes.
6. Document the provider's webhook URL and least-privilege credential requirements.

## Stripe

Install with `pip install ".[stripe]"` or set
`INVOICE_MACHINE_EXTRAS=stripe` while building the Compose image. In Settings, enter a
restricted/test secret key and the endpoint signing secret, test the connection, and
then explicitly allow online links. Use this webhook endpoint:

`POST /api/payments/stripe/webhook`

Checkout sessions contain the invoice ID, expected amount in minor units, and currency
as metadata. Webhooks are signature-checked and these values are compared before the
ledger is updated. A stale checkout that would overpay an edited or manually settled
invoice is retained as `needs_review` rather than silently applied.
