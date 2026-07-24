# Contributing

Thanks for taking an interest. This is a small, deliberately focused project, so
the fastest route to a merged change is a short issue describing the problem
before you write the code.

## Getting set up

```bash
# Backend
pip install -e ".[dev]"
uvicorn invoice_machine.main:app --reload --port 8080

# Frontend, in a second terminal
cd frontend && npm install && npm run dev
```

The backend serves the API on 8080 and the Vite dev server proxies to it. A
SQLite database is created under `data/` on first run.

## Before you open a pull request

```bash
ruff check invoice_machine/ tests/
pytest -q
cd frontend && npm run check && npm run build
```

CI runs exactly these, plus a Docker build and a dependency audit. Coverage must
stay at or above 70%.

## What good looks like here

**Money is `Decimal`, quantized to two places, and never summed across
currencies.** Totals are reported per currency. The one consolidated view is
opt-in and reports what it could not convert rather than guessing a rate. If a
change makes it possible to add dollars to euros, it will be sent back.

**Alembic is the source of truth for the schema.** Every model change needs a
migration. `tests/test_schema_drift.py` runs the migrations against a throwaway
database and fails if the two disagree. Never edit a migration that has shipped;
add a new one.

**Migrations must consider existing data, not just the schema.** A column added
with a default is only half the job if live rows need backfilling. Migration 015
exists because 014 added `amount_paid` without it, and every already-paid
invoice started reporting a full balance due.

**Comments explain why, not what.** The code says what it does. A comment earns
its place by recording the reason a non-obvious choice was made, usually the bug
that would come back if someone simplified it.

**Tests should fail for the right reason.** A test that passes before your fix
is not a regression test. Where practical, write the test first and watch it
fail.

## Architecture in one minute

```
invoice_machine/
├── api/        HTTP layer: validation, status codes, no business logic
├── service/    Business logic, the only place that changes data
├── mcp/        MCP tools, thin wrappers over service/
├── pdf/        WeasyPrint rendering
└── alembic/    Migrations
```

REST and MCP both call `service/`, which is what keeps the two surfaces from
drifting. If you add a capability to one, add it to the other or say why not.

## Reporting security issues

Please do not open a public issue. See [SECURITY.md](SECURITY.md).
