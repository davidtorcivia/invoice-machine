## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The problem being solved. For a bug, what went wrong and why. -->

## Checklist

- [ ] `ruff check invoice_machine/ tests/` passes
- [ ] `pytest -q` passes
- [ ] `npm run check && npm run build` passes, if the frontend changed
- [ ] Schema changes have an Alembic migration, and existing rows are backfilled if they need it
- [ ] New behaviour has a test that fails without the change
- [ ] REST and MCP both updated, or a note below on why only one
