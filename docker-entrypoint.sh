#!/bin/bash
set -e

# Fix ownership of the data directory if running as root, then drop privileges.
# We re-exec THIS entrypoint (not the CMD directly) so migrations below run as
# the unprivileged appuser.
if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /app/data 2>/dev/null || true
    exec gosu appuser "$0" "$@"
fi

# Apply database migrations before starting the app. `set -e` ensures the
# container fails to start if migrations fail, rather than serving a broken
# schema. Running here (single process) avoids multi-worker migration races.
# prepare_runtime renames a legacy invoicely.db first, and run_alembic_migrations
# remaps old revision ids and refuses a pre-Alembic database.
echo "Running database migrations..."
python -c "from invoice_machine.config import prepare_runtime; from invoice_machine.runtime_schema import run_alembic_migrations; prepare_runtime(); run_alembic_migrations()"

# uvicorn rewrites request.client from X-Forwarded-For when proxy-headers are
# on. That must track TRUST_PROXY_HEADERS or a client can pick its rate-limit key.
if [ "$1" = "uvicorn" ]; then
    case "${TRUST_PROXY_HEADERS}" in
        1|true|True|TRUE|yes|YES|on|ON)
            set -- "$@" --proxy-headers --forwarded-allow-ips "*"
            ;;
        *)
            set -- "$@" --no-proxy-headers
            ;;
    esac
fi

exec "$@"
